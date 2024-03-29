import os
import math
import random
import sys
import matplotlib.pyplot as plt

import imageio
import numpy as np
from PIL import Image, ImageSequence
from accelerate import Accelerator
from accelerate.logging import get_logger
from accelerate.utils import set_seed
from einops import rearrange
from typing import Any, Callable, Dict, List, Optional, Union, Tuple
from tqdm.auto import tqdm
import click
from omegaconf import OmegaConf
import yaml

import torch
import torch.nn.functional as F
from torchvision.transforms.functional import to_tensor
import torch.fft as fft
from pytorch_wavelets import DWT1DForward, DWT1DInverse

from diffusers import DDPMScheduler, DDIMScheduler, DPMSolverMultistepScheduler, DPMSolverSinglestepScheduler
from diffusers import IFSuperResolutionPipeline, DiffusionPipeline, VideoToVideoSDPipeline
from diffusers.utils import export_to_video, randn_tensor
from diffusers.optimization import get_scheduler

from showone.models import UNet3DConditionModel
from showone.pipelines import TextToVideoIFPipeline, TextToVideoIFInterpPipeline, TextToVideoIFSuperResolutionPipeline
from showone.pipelines.pipeline_t2v_base_pixel import tensor2vid
from showone.pipelines.pipeline_t2v_sr_pixel_cond import TextToVideoIFSuperResolutionPipeline_Cond

from transformers import CLIPImageProcessor, T5EncoderModel, T5Tokenizer
from data.dataset import ImageSequenceDataset
from common.image_util import make_grid, annotate_image, save_images_as_gif
from common.util import get_time_string, get_function_args, ddim_inversion


logger = get_logger(__name__)


def collate_fn(examples):
    batch = {
        "prompt_ids": torch.cat([example["prompt_ids"] for example in examples], dim=0),
        "images": torch.stack([example["images"] for example in examples]),
    }
    return batch


def log_train_samples(
    train_dataloader,
    save_path,
    num_batch: int = 4):
    train_samples = []
    for idx, batch in enumerate(train_dataloader):
        if idx >= num_batch:
            break
        train_samples.append(batch["images"])

    train_samples = torch.cat(train_samples).numpy()
    train_samples = rearrange(train_samples, "b c f h w -> b f h w c")
    train_samples = (train_samples * 0.5 + 0.5).clip(0, 1)
    train_samples = numpy_to_pil(train_samples)
    train_samples = [make_grid(images, cols=1) for images in zip(*train_samples)]
    save_images_as_gif(train_samples, save_path)


def numpy_to_pil(images):
        pil_images = []
        for sequence in images:
            pil_images.append(TextToVideoIFPipeline.numpy_to_pil(sequence))
        return pil_images

def w_low_freq_local(height, width, delta=0.05, base=1.):
    rows = torch.arange(height, dtype=torch.float32)
    cols = torch.arange(width, dtype=torch.float32)

    rows, cols = torch.meshgrid(rows, cols)

    coefficient_matrix = (rows - height / 2)**2 + (cols - width / 2)**2
    w_low_freq = ((height/2) ** 2 + (width/2) ** 2) ** delta - coefficient_matrix ** delta + base

    return w_low_freq

def sma_local(images, v0hat, accelerator, delta=0.05, base=1.):
    b,c,f,h,w = images.shape
    img_residuals = torch.abs(images[:, :, 1:, :, :] - images[:, :, :-1, :, :])
    fft_img_residuals = fft.fftn(img_residuals.float(), dim=(-2, -1))
    fft_img_residuals = fft.fftshift(fft_img_residuals, dim=(-2, -1))
    magnitude_img_residuals = torch.abs(fft_img_residuals)
    phase_img_residuals = torch.angle(fft_img_residuals)

    v0hat_residuals = torch.abs(v0hat[:, :, 1:, :, :] - v0hat[:, :, :-1, :, :])
    fft_v0hat_residuals = fft.fftn(v0hat_residuals.float(), dim=(-2, -1))
    fft_v0hat_residuals = fft.fftshift(fft_v0hat_residuals, dim=(-2, -1))
    magnitude_v0hat_residuals = torch.abs(fft_v0hat_residuals)
    phase_v0hat_residuals = torch.angle(fft_v0hat_residuals)

    w_low_freq = w_low_freq_local(h, w, delta=delta, base=base).to(accelerator.device).reshape(1,1,1,h,w)

    loss_sma_mag = torch.mean(torch.abs(magnitude_img_residuals.float() - magnitude_v0hat_residuals.float()) * w_low_freq)
    loss_sma_phase = torch.mean(torch.abs(phase_img_residuals.float() - phase_v0hat_residuals.float()) * w_low_freq)
    loss_sma_local = loss_sma_mag + loss_sma_phase
    return loss_sma_local

def sma_global(images, v0hat, wavelet_type='haar', num_levels=3, ld_levels=[1., 1., 1., 1.]):
    b,c,f,h,w = images.shape
    images = images.permute(0, 1, 3, 4, 2).reshape(b, c*h*w, f).float() 
    v0hat = v0hat.permute(0, 1, 3, 4, 2).reshape(b, c*h*w, f).float() 

    img_residuals = torch.abs(images[:, :, 1:] - images[:, :, :-1])
    v0hat_residuals = torch.abs(v0hat[:, :, 1:] - v0hat[:, :, :-1])

    dwt = DWT1DForward(wave=wavelet_type, J=num_levels).cuda()
    images_l, images_h = dwt(img_residuals)
    v0hat_l, v0hat_h = dwt(v0hat_residuals)

    l1_loss = 0.0
    l1_loss += torch.abs(images_l - v0hat_l).mean() * ld_levels[0]

    for i, (c1, c2) in enumerate(zip(images_h, v0hat_h)):
        l1_loss += torch.abs(c1 - c2).mean() * ld_levels[i + 1]
    return l1_loss


class SampleLogger:
    def __init__(
        self,
        prompts: List[str],
        clip_length: int,
        logdir: str,
        subdir: str = "validations",
        num_samples_per_prompt: int = 1,
        sample_seeds: List[int] = None,
        num_inference_steps: int = 75,
        guidance_scale: float = 9.0,
        annotate: bool = False,
        annotate_size: int = 6,
        make_grid: bool = True,
        grid_column_size: int = 2,
        height: int = 40,
        width: int = 64,) -> None:
        self.prompts = prompts
        self.clip_length = clip_length
        self.guidance_scale = guidance_scale
        self.num_inference_steps = num_inference_steps
        self.height = height
        self.width = width

        if sample_seeds is None:
            max_num_samples_per_prompt = int(1e5)
            if num_samples_per_prompt > max_num_samples_per_prompt:
                raise ValueError
            sample_seeds = torch.randint(0, max_num_samples_per_prompt, (num_samples_per_prompt,))
            sample_seeds = sorted(sample_seeds.numpy().tolist())
        self.sample_seeds = sample_seeds

        self.logdir = os.path.join(logdir, subdir)
        os.makedirs(self.logdir)

        self.annotate = annotate
        self.annotate_size = annotate_size
        self.make_grid = make_grid
        self.grid_column_size = grid_column_size

    def log_sample_images(
        self, pipeline: TextToVideoIFPipeline, device: torch.device, step: int, inv_images: Optional[torch.FloatTensor]=None,
    ):
        samples_all = []
        save_dir = os.path.join(self.logdir, f"step_{step}")
        os.makedirs(save_dir, exist_ok=True)
        for idx, prompt in enumerate(tqdm(self.prompts, desc="Generating sample images")):
            for seed in self.sample_seeds:
                prompt_embeds, negative_embeds = pipeline.encode_prompt(prompt)
                sequence = pipeline(
                    inv_images=inv_images,
                    prompt_embeds=prompt_embeds,
                    negative_prompt_embeds=negative_embeds,
                    generator=torch.manual_seed(seed),
                    num_inference_steps=self.num_inference_steps,
                    num_frames=self.clip_length,
                    guidance_scale=self.guidance_scale,
                    num_images_per_prompt=1,
                    height=self.height,
                    width=self.width,
                    output_type="pt",
                ).frames
                
                imageio.mimsave(
                    f"{save_dir}/{idx}_base.gif",
                    tensor2vid(sequence.clone()),
                    fps=2)

        # if self.make_grid:
        #     samples_all = [make_grid(images, cols=2) for images in zip(*samples_all)]
        #     #save_images_as_gif(samples_all, os.path.join(save_dir, "grid_base.gif"))
        #     imageio.mimsave( os.path.join(save_dir, "grid_base.gif"), fps=2 )


def train(
    pretrained_t2v_path: str = "showlab/show-1-base",
    ddim_inv_scheduler_path: str = "/mnt/ssd8/hyeonho/stable-diffusion-v1-5/scheduler",
    vid_name: str = "some-video-name",
    exp_name: str = "",
    gradient_accumulation_steps: int = 1,
    mixed_precision: Optional[str] = "fp16",
    gradient_checkpointing: bool = True,
    scale_lr: bool = False,
    lr: float = 3e-5,   # TRY: either 1e-5 or 3e-5 or 1e-4
    train_batch_size: int = 1,
    adam_weight_decay: float=1e-2,
    adam_epsilon: float=1e-8,
    logdir: str = "outputs",
    lr_scheduler: str = "constant",  # ["linear", "cosine", "cosine_with_restarts", "polynomial", "constant", "constant_with_warmup"]
    lr_warmup_steps: int = 0,
    train_steps: int = 500,
    validation_steps: int = 100,
    train_dataset: Dict = None,
    validation_sample_logger: Dict = None,
    seed: int = 12345,
    max_grad_norm: float = 1.0,
    num_inv_steps: int = 30,
    threshold: float = 0.2,
    trainable_modules: Tuple = (".to_q", ".to_k", ".to_v"),
    save_config: bool = True,
    sr2_strength: float = 0.8,
    sr2_steps: int = 50,
    ld_global: float = 0.5, 
    ld_local: float = 0.2,
    num_levels: int = 2,
    ld_levels: List[float] = [1., 1., 1.],
):  

    vid_name = vid_name
    time_str = get_time_string()
    logdir = os.path.join(logdir, vid_name, f'{time_str}{exp_name}')
    os.makedirs(logdir, exist_ok=True)

    # save config file
    if save_config:
        inference_prompts = [ f"{i}: " + p for i,p in enumerate(validation_sample_logger["prompts"]) ]
        config_dict = OmegaConf.create(
            {
                "train_steps": train_steps,
                "lr" : lr,
                "num_inv_steps":num_inv_steps,
                "threshold":threshold,
                "trainable_modules": trainable_modules,
                "seed": seed,
                "train_prompt":train_dataset["prompt"],
                "inference_prompts":inference_prompts,
                "sr2_strength": sr2_strength,
                "sr2_steps": sr2_steps,
                "ld_global": ld_global,
                "ld_local": ld_local,
                "num_levels": num_levels,
                "ld_levels": ld_levels
            })
        OmegaConf.save(config_dict, os.path.join(logdir, "config.yaml"))

    if seed is not None:
        set_seed(seed)
        torch.manual_seed(seed)

    # configure accelerator
    accelerator = Accelerator(
        gradient_accumulation_steps=gradient_accumulation_steps,
        mixed_precision=mixed_precision,
    )
    weight_dtype = torch.float16

    if True:
        # Load [key-frame generation] pipeline #
        pipe_base = TextToVideoIFPipeline.from_pretrained(
            pretrained_t2v_path,
            torch_dtype=torch.float16,
            variant="fp16"
        )
        pipe_base.enable_model_cpu_offload()
        print("key-frame generation pipeline loaded\n")
        # = = = = = = = = = = = = = = = = = = #

        # Load [frame interpolation] pipeline #
        pretrained_model_path = "showlab/show-1-interpolation" # hf: "showlab/show-1-interpolation"
        pipe_interp_1 = TextToVideoIFInterpPipeline.from_pretrained(
            pretrained_model_path, torch_dtype=torch.float16, variant="fp16")
        pipe_interp_1.enable_model_cpu_offload()
        print("frame interpolation loaded\n")
        # = = = = = = = = = = = = = = = = = = #

        # Load [super resolution 1-1 (pixel space)] pipeline #    
        pretrained_model_path = "DeepFloyd/IF-II-L-v1.0" # hf: "DeepFloyd/IF-II-L-v1.0"
        pipe_sr_1_image = IFSuperResolutionPipeline.from_pretrained(
            pretrained_model_path, text_encoder=None, variant="fp16", torch_dtype=torch.float16)
        pipe_sr_1_image.enable_model_cpu_offload()
        print("image sr loaded loaded\n")
        # = = = = = = = = = = = = = = = = = = #

        # Load [super resolution 1-2 (pixel space)] pipeline #
        pretrained_model_path = "showlab/show-1-sr1" # hf: "showlab/show-1-sr1"
        pipe_sr_1_cond = TextToVideoIFSuperResolutionPipeline_Cond.from_pretrained(
            pretrained_model_path, torch_dtype=torch.float16)
        pipe_sr_1_cond.enable_model_cpu_offload()
        print("spatial sr1 (pixel-based) loaded\n")
        # = = = = = = = = = = = = = = = = = = = = = = = = = = = = #


        # Load [super resolution 2 (latent space)] pipeline #
        pretrained_model_path = "showlab/show-1-sr2" # hf: "showlab/show-1-sr2"
        pipe_sr_2 = VideoToVideoSDPipeline.from_pretrained(
            pretrained_model_path, torch_dtype=torch.float16)
        pipe_sr_2.enable_model_cpu_offload()
        pipe_sr_2.enable_vae_slicing()
        print("spatial sr2 (latent-based) loaded\n")
        # = = = = = = = = = = = = = = = = = = = = = = = = = = = = #


    # Load [key-frame generation] modules #
    pipe_base_components = pipe_base.components
    base_tokenizer = pipe_base_components["tokenizer"]
    base_text_encoder = pipe_base_components["text_encoder"]
    #base_feature_extractor = pipe_base_components["feature_extractor"]
    base_unet = pipe_base_components["unet"].to(dtype=torch.float32)
    base_scheduler = pipe_base_components["scheduler"]    

    # freeze all
    base_text_encoder.requires_grad_(False)
    base_unet.requires_grad_(False)
    
    # unfreeze all projection layers of Temporal Attentions
    for name, module in base_unet.named_modules():
        if "temp_attentions" in name and name.endswith( tuple(trainable_modules) ):
            for params in module.parameters():
                params.requires_grad = True

    if gradient_checkpointing:
        base_unet.enable_gradient_checkpointing()

    if scale_lr:
        lr = ( lr * gradient_accumulation_steps * train_batch_size * accelerator.num_processes )

    params_to_optimize = base_unet.parameters()
    optimizer = torch.optim.AdamW(
        params_to_optimize,
        lr=lr,
        betas=(0.9, 0.999),
        weight_decay=adam_weight_decay,
        eps=adam_epsilon,
    )

    # load train dataset
    prompt_ids = base_tokenizer(
                train_dataset["prompt"],
                padding="max_length",
                max_length=77, 
                truncation=True,
                add_special_tokens=True,
                return_tensors="pt",
    ).input_ids[0]
    train_dataset = ImageSequenceDataset( **train_dataset, prompt_ids = prompt_ids )
    train_dataloader = torch.utils.data.DataLoader(
        train_dataset,
        batch_size=train_batch_size,
        shuffle=False,
        collate_fn=collate_fn,
    )

    train_sample_save_path = os.path.join(logdir, "train_samples.gif")
    log_train_samples(train_dataloader, train_sample_save_path)

    lr_scheduler = get_scheduler(
        lr_scheduler,
        optimizer=optimizer,
        num_warmup_steps=lr_warmup_steps * gradient_accumulation_steps,
        num_training_steps=train_steps * gradient_accumulation_steps,
    )

    # accelerator.prepare
    base_unet, optimizer, train_dataloader, lr_scheduler = accelerator.prepare(
        base_unet, optimizer, train_dataloader, lr_scheduler
    )
    accelerator.register_for_checkpointing(lr_scheduler)
    base_text_encoder.to(accelerator.device)
    base_text_encoder.eval()


    # ddim inv scheduler
    if num_inv_steps > 0:
        ddim_inv_scheduler = DDIMScheduler.from_pretrained(ddim_inv_scheduler_path)
        ddim_inv_scheduler.set_timesteps(num_inv_steps)

    # We need to initialize the trackers we use, and also store our configuration.
    # The trackers initializes automatically on the main process.
    if accelerator.is_main_process:
        accelerator.init_trackers("video")  # , config=vars(args))
    
    # [Train]
    total_batch_size = train_batch_size * accelerator.num_processes * gradient_accumulation_steps

    logger.info("***** Running training *****")
    logger.info(f"  Num examples = {len(train_dataset)}")
    logger.info(f"  Num batches each epoch = {len(train_dataloader)}")
    logger.info(f"  Instantaneous batch size per device = {train_batch_size}")
    logger.info(f"  Total train batch size (w. parallel, distributed & accumulation) = {total_batch_size}")
    logger.info(f"  Gradient Accumulation steps = {gradient_accumulation_steps}")
    logger.info(f"  Total optimization steps = {train_steps}")
    step = 0

    if validation_sample_logger is not None and accelerator.is_main_process:
        validation_sample_logger = SampleLogger(**validation_sample_logger, logdir=logdir)

    progress_bar = tqdm(
        range(step, train_steps),
        disable=not accelerator.is_local_main_process,
    )
    progress_bar.set_description("Training Steps [KFG]")

    def make_data_yielder(dataloader):
        while True:
            for batch in dataloader:
                yield batch
            accelerator.wait_for_everyone()

    train_data_yielder = make_data_yielder(train_dataloader)
    sampled_timesteps = torch.randint(0, base_scheduler.config.num_train_timesteps, (train_batch_size, train_steps), device=accelerator.device)
    prompt_embeds, _ = pipe_base.encode_prompt(train_dataset.prompt)
    alphas = base_scheduler.alphas_cumprod.to(accelerator.device)

    while step < train_steps:
        
        batch = next(train_data_yielder)
        base_unet.train()

        with accelerator.accumulate(base_unet):
            images = batch["images"].to(dtype=weight_dtype)
            b,c,f,h,w = images.shape    # (1, 3, 8, 40, 64)

            noise = torch.randn_like(images)
            timestep = sampled_timesteps[:, step]
            timestep.long()

            # add noise to the x_0 (forward diffusion)
            noisy_intermediate_images = base_scheduler.add_noise(images, noise, timestep)

            # predict noise residual
            model_pred = base_unet(
                        noisy_intermediate_images,
                        timestep,
                        encoder_hidden_states=prompt_embeds,
                        ).sample

            if pipe_base.scheduler.config.variance_type not in ["learned", "learned_range"]:
                model_pred, _ = model_pred.split(noisy_intermediate_images.shape[1], dim=1)
            
            # Tweedie's denoised estimate
            alpha_t = alphas[timestep, None, None, None, None]
            v0hat = (noisy_intermediate_images - (1. - alpha_t) ** (0.5) * model_pred) / alpha_t ** (0.5)

            assert base_scheduler.config.prediction_type == "epsilon"
            target = noise
            
            loss = 0

            model_pred_residual = torch.abs(model_pred[:, :, 1:, :, :] - model_pred[:, :, :-1, :, :])
            target_residual = torch.abs(target[:, :, 1:, :, :] - target[:, :, :-1, :, :])
            loss = loss + (1 - F.cosine_similarity(model_pred_residual, target_residual, dim=2).mean())

            loss_sma_local = sma_local(images, v0hat, accelerator, delta=0.05, base=1.)
            loss_sma_global = sma_global(images, v0hat, num_levels=num_levels, ld_levels=ld_levels, wavelet_type='haar')

            loss = loss + ld_global * loss_sma_global + ld_local * loss_sma_local

            # update weights
            accelerator.backward(loss)
            if accelerator.sync_gradients:
                accelerator.clip_grad_norm_(base_unet.parameters(), max_grad_norm)
            optimizer.step()
            lr_scheduler.step()
            optimizer.zero_grad()

        if accelerator.sync_gradients:
            progress_bar.update(1)
            step += 1

            if accelerator.is_main_process:
                if validation_sample_logger is not None and step % validation_steps == 0:
                    base_unet.eval()
                    inv_images = None
                    if num_inv_steps > 0:
                        inv_images = ddim_inversion(
                            pipeline=pipe_base, 
                            ddim_scheduler=ddim_inv_scheduler, 
                            video_latent=images, 
                            num_inv_steps=num_inv_steps
                        )[-1].to(weight_dtype)

                    for idx, val_prompt in enumerate(validation_sample_logger.prompts):
                        inference(
                            pipe_base=pipe_base,
                            pipe_interp_1=pipe_interp_1,
                            pipe_sr_1_image=pipe_sr_1_image,
                            pipe_sr_1_cond=pipe_sr_1_cond,
                            pipe_sr_2=pipe_sr_2,
                            inv_images=inv_images,
                            prompt=val_prompt,
                            prompt_idx=idx,
                            seed=seed,
                            output_dir=os.path.join(validation_sample_logger.logdir, f"step_{step}"),
                            sr2_strength=sr2_strength,
                            sr2_steps=sr2_steps,
                        )
            
        logs = {"loss": loss.detach().item(), "lr":lr_scheduler.get_last_lr()[0]}
        progress_bar.set_postfix(**logs)
        accelerator.log(logs, step=step)

    accelerator.end_training()


def inference(pipe_base, pipe_interp_1, pipe_sr_1_image, pipe_sr_1_cond, pipe_sr_2,
               inv_images, prompt, prompt_idx, seed, output_dir, sr2_strength, sr2_steps):

    negative_prompt = "low resolution, blur"
    os.makedirs(output_dir, exist_ok=True)

    # text embeds
    prompt_embeds, negative_embeds = pipe_base.encode_prompt(prompt)


    # - - - - - - - - keyframes generation - - - - - - - - #
    video_frames = pipe_base(
                            inv_images=inv_images,
                            prompt_embeds=prompt_embeds,
                            negative_prompt_embeds=negative_embeds,
                            num_frames=8,
                            height=40,
                            width=64,
                            num_inference_steps=75,
                            guidance_scale=9.0,
                            generator=torch.manual_seed(seed),
                            output_type="pt").frames

    imageio.mimsave(f"{output_dir}/{prompt_idx}_base.gif",
                    tensor2vid(video_frames.clone()),
                    fps=2)
    # - - - - - - - - - - - - - - - - - - - - - - - - - - - #

    # - - CONVERT DTYPE OF video_frames (fp32 -> fp16) - - #
    video_frames = video_frames.to(dtype=torch.float16)


    # - - - - - - interpolation (2fps -> 7.5fps) - - - - - - #
    bsz, channel, num_frames, height, width = video_frames.shape
    new_num_frames = 3 * (num_frames - 1) + num_frames
    new_video_frames = torch.zeros((bsz, channel, new_num_frames, height, width),
                                dtype=video_frames.dtype,
                                device=video_frames.device)
    new_video_frames[:, :, torch.arange(0, new_num_frames, 4), ...] = video_frames

    from diffusers.utils.torch_utils import randn_tensor

    init_noise = randn_tensor((bsz, channel, 5, height, width),
                            generator=torch.manual_seed(seed),
                            device=video_frames.device,
                            dtype=video_frames.dtype)

    for i in range(num_frames - 1):
        batch_i = torch.zeros((bsz, channel, 5, height, width),
                            dtype=video_frames.dtype,
                            device=video_frames.device)
        batch_i[:, :, 0, ...] = video_frames[:, :, i, ...]
        batch_i[:, :, -1, ...] = video_frames[:, :, i + 1, ...]
        batch_i = pipe_interp_1(
            pixel_values=batch_i,
            prompt_embeds=prompt_embeds,
            negative_prompt_embeds=negative_embeds,
            num_frames=batch_i.shape[2],
            height=40,
            width=64,
            num_inference_steps=75,
            guidance_scale=4.0,
            generator=torch.manual_seed(seed),
            output_type="pt",
            init_noise=init_noise,
            cond_interpolation=True,
        ).frames

        new_video_frames[:, :, i * 4:i * 4 + 5, ...] = batch_i

    video_frames = new_video_frames
    imageio.mimsave(f"{output_dir}/{prompt_idx}_inter.gif",
                    tensor2vid(video_frames.clone()),
                    fps=8)
    # - - - - - - - - - - - - - - - - - - - - - - - - - - - #


    # - - - - - - - - - - sr1 - - - - - - - - - - #
    bsz, channel, num_frames, height, width = video_frames.shape
    window_size, stride = 8, 7
    if num_frames == 61:
        window_size, stride = 7,6
    new_video_frames = torch.zeros(
        (bsz, channel, num_frames, height * 4, width * 4),
        dtype=video_frames.dtype,
        device=video_frames.device)
    for i in range(0, num_frames - window_size + 1, stride):
        batch_i = video_frames[:, :, i:i + window_size, ...]
        all_frame_cond = None

        if i == 0:
            first_frame_cond = pipe_sr_1_image(
                image=video_frames[:, :, 0, ...],
                prompt_embeds=prompt_embeds,
                negative_prompt_embeds=negative_embeds,
                height=height * 4,
                width=width * 4,
                num_inference_steps=70,
                guidance_scale=4.0,
                noise_level=150,
                generator=torch.manual_seed(seed),
                output_type="pt").images
            first_frame_cond = first_frame_cond.unsqueeze(2)
        else:
            first_frame_cond = new_video_frames[:, :, i:i + 1, ...]

        batch_i = pipe_sr_1_cond(image=batch_i,
                                prompt_embeds=prompt_embeds,
                                negative_prompt_embeds=negative_embeds,
                                first_frame_cond=first_frame_cond,
                                height=height * 4,
                                width=width * 4,
                                num_inference_steps=125,
                                guidance_scale=7.0,
                                noise_level=250,
                                generator=torch.manual_seed(seed),
                                output_type="pt").frames
        new_video_frames[:, :, i:i + window_size, ...] = batch_i

    video_frames = new_video_frames
    imageio.mimsave(f"{output_dir}/{prompt_idx}_sr1.gif",
                    tensor2vid(video_frames.clone()),
                    fps=8)
    # - - - - - - - - - - - - - - - - - - - - - - #


    # - - - - - - - - - - sr1 - - - - - - - - - - #
    video_frames = [
        Image.fromarray(frame).resize((576, 320))
        for frame in tensor2vid(video_frames.clone())
    ]
    video_frames = pipe_sr_2(prompt,
                            negative_prompt=negative_prompt,
                            video=video_frames,
                            strength=sr2_strength, 
                            num_inference_steps=sr2_steps, 
                            generator=torch.manual_seed(seed),
                            output_type="pt").frames

    imageio.mimsave(f"{output_dir}/{prompt_idx}.gif",
                    tensor2vid(video_frames.clone()),
                    fps=8)
    # - - - - - - - - - - - - - - - - - - - - - - - #



@click.command()
@click.option("--config", type=str, default="config/car.yml")
@click.option("--exp_name", type=str, default="")

def run(config, exp_name):
    param_dict = OmegaConf.load(config)
    if not exp_name == "":
        param_dict.update({'exp_name': exp_name})
    train(**param_dict)

if __name__ == "__main__":
    run()

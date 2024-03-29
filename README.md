# Spectral-Motion-Alignment
This repository is the official implementation of [SMA: Spectral Motion Alignment for Video Motion Transfer using Diffusion Models](https://arxiv.org/abs/2403.15249).<br>
[Geon Yeong Park*](https://geonyeong-park.github.io/),
[Hyeonho Jeong*](https://hyeonho99.github.io/),
[Sang Wan Lee](https://aibrain.kaist.ac.kr/),
[Jong Chul Ye](https://bispl.weebly.com/)

[![Project Website](https://img.shields.io/badge/Project-Website-orange)](https://geonyeong-park.github.io/spectral-motion-alignment/)
[![arXiv](https://img.shields.io/badge/arxiv-2403.15249-b31b1b)](https://arxiv.org/abs/2403.15249)

<p align="center">
<img src="https://geonyeong-park.github.io/spectral-motion-alignment/static/images/SMA_model.png" width="100%"/>
<br>
<em>SMA framework distills the motion information in frequency-domain. Our regularization includes (1) global motion alignment based on 1D wavelet-transform, and (2) local motion refinement based on 2D Fourier transform. </em>
</p>

## News
* [2024.03.29] Initial Code Release

## Setup
### Requirements
For the preliminary proof of concepts, this repository is build upon [VMC (w/ Show-1 backbone)](https://github.com/HyeonHo99/Video-Motion-Customization/tree/main).
(1) Install VMC requirements

```shell
pip install -r requirements.txt
```

(2) Install wavelet libraries

- [pytorch_wavelets](https://github.com/fbcotter/pytorch_wavelets)
```shell
git clone https://github.com/fbcotter/pytorch_wavelets
cd pytorch_wavelets
pip install .
```
- [PyWavelets](https://pywavelets.readthedocs.io/en/latest/install.html)
```shell
pip install PyWavelets
```

## Usage

The following command will run "train & inference" at the same time:

```bash
accelerate launch train_inference.py --config configs/man_skate.yml
```

## Additional Data
Following samples are released by [VMC](https://github.com/HyeonHo99/Video-Motion-Customization/tree/main).
* PNG files: [Google Drive Folder](https://drive.google.com/drive/u/2/folders/1L4dIqeK52lGBuxIKAEUzZgOEP95dz7AC)
* GIF files: [Google Drive Folder](https://drive.google.com/drive/u/2/folders/1GUDnosOkYQ50-1bHHIBitRMeamkd2qao)

## Results
<table class="center">
  <tr>
    <td style="text-align:center;"><b>Input Videos</b></td>
    <td style="text-align:center;" colspan="1"><b>Output Videos</b></td>
  </tr>
  <tr>
    <td><img src="https://geonyeong-park.github.io/spectral-motion-alignment/static/gifs/long/penguins_swimming2/input.gif"></td>
    <td><img src="https://geonyeong-park.github.io/spectral-motion-alignment/static/gifs/long/penguins_swimming2/shark.gif"></td>
  </tr>
  <tr>
    <td><img src="https://geonyeong-park.github.io/spectral-motion-alignment/static/gifs/demo/man_skate/input.gif"></td>
    <td><img src="https://geonyeong-park.github.io/spectral-motion-alignment/static/gifs/demo/man_skate/astronaut_snow.gif"></td>
  </tr>
  <tr>
    <td><img src="https://geonyeong-park.github.io/spectral-motion-alignment/static/gifs/vmc_show1/cars_bridge1/input.gif"></td>
    <td><img src="https://geonyeong-park.github.io/spectral-motion-alignment/static/gifs/vmc_show1/cars_bridge1/with/turtle.gif"></td>
  </tr>
  <tr>
    <td><img src="https://geonyeong-park.github.io/spectral-motion-alignment/static/gifs/vmc_show1/rabbit_strawberry/input.gif"></td>
    <td><img src="https://geonyeong-park.github.io/spectral-motion-alignment/static/gifs/vmc_show1/rabbit_strawberry/with/raccoon_nuts.gif"></td>
  </tr>
  <tr>
    <td><img src="https://geonyeong-park.github.io/spectral-motion-alignment/static/gifs/vmc_show1/penguins_swimming1/input.gif"></td>
    <td><img src="https://geonyeong-park.github.io/spectral-motion-alignment/static/gifs/vmc_show1/penguins_swimming1/with/spaceships_space.gif"></td>
  </tr>
  <tr>
    <td><img src="https://geonyeong-park.github.io/spectral-motion-alignment/static/gifs/vmc_show1/butterfly/input.gif"></td>
    <td><img src="https://geonyeong-park.github.io/spectral-motion-alignment/static/gifs/vmc_show1/butterfly/with/snow.gif"></td>
  </tr>
</table>

### More results (w/ [MotionDirector](https://github.com/showlab/MotionDirector))
<table class="center">
  <tr>
    <td style="text-align:center;"><b>Input Videos</b></td>
    <td style="text-align:center;" colspan="1"><b>Output Videos</b></td>
  </tr>
  <tr>
    <td><img src="https://geonyeong-park.github.io/spectral-motion-alignment/static/gifs/motiondirector/seagull_walking/input.gif"></td>
    <td><img src="https://geonyeong-park.github.io/spectral-motion-alignment/static/gifs/motiondirector/seagull_walking/with/chicken.gif"></td>
  </tr>
  <tr>
    <td><img src="https://geonyeong-park.github.io/spectral-motion-alignment/static/gifs/motiondirector/seagull_skyline/input.gif"></td>
    <td><img src="https://geonyeong-park.github.io/spectral-motion-alignment/static/gifs/motiondirector/seagull_skyline/with/eagle.gif"></td>
  </tr>
  <tr>
    <td><img src="https://geonyeong-park.github.io/spectral-motion-alignment/static/gifs/motiondirector/sharks_moving/input.gif"></td>
    <td><img src="https://geonyeong-park.github.io/spectral-motion-alignment/static/gifs/motiondirector/sharks_moving/with/airplane_sky.gif"></td>
  </tr>
</table>

### Hyperparameters
Most configurations follows [VMC](https://github.com/HyeonHo99/Video-Motion-Customization/tree/main).
- `ld_global`: Weight for global motion alignment ($\lambda_{g}$ in the paper). Recommend `0.4` for a first trial.

- `ld_local`: Weight for local motion refinement ($\lambda_{l}$ in the paper). Recommend `0.2` for a first trial.

- `num_levels`: Number of levels in discrete wavelet transform. Recommend `2` for 8-frames, `3` for 16-frames.

- `ld_levels`: Weight for the alignment of each wavelet coefficients. Recommend default setting: [1]*(num_levels+1).

## Citation
If you find our work interesting, please cite our paper.
```bibtex
@article{park2024spectral,
  title={Spectral Motion Alignment for Video Motion Transfer using Diffusion Models},
  author={Park, Geon Yeong and Jeong, Hyeonho and Lee, Sang Wan and Ye, Jong Chul},
  journal={arXiv preprint arXiv:2403.15249},
  year={2024}
}
```

## Shoutouts
- SMA directly employs an open-source project on cascaded Video Diffusion Models, [Show-1](https://github.com/showlab/Show-1),
  along with [DeepFloyd IF](https://github.com/deep-floyd/IF), as similarly done by [VMC](https://github.com/HyeonHo99/Video-Motion-Customization/tree/main).
- This code builds upon [Diffusers](https://github.com/huggingface/diffusers) and we referenced the code logic of [Tune-A-Video](https://github.com/showlab/Tune-A-Video).
- We demonstrated the compatibility of SMA with our previous work (VMC) and other three great projects: [MotionDirector](https://arxiv.org/abs/2310.08465), [Tune-A-Video](https://arxiv.org/abs/2212.11565), [Control-A-Video](https://arxiv.org/abs/2305.13840).

<br><i>Thanks all for open-sourcing!</i>



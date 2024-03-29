# Spectral-Motion-Alignment
This repository is the official implementation of [SMA](https://arxiv.org/abs/2403.15249).<br>
**[SMA: Spectral Motion Alignment for Video Motion Transfer using Diffusion Models](https://arxiv.org/abs/2403.15249).** <br>
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
We benefit from video dataset released by [VMC](https://github.com/HyeonHo99/Video-Motion-Customization/tree/main).
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
</table>

## Hyperparameters
Most configurations follows [VMC](https://github.com/HyeonHo99/Video-Motion-Customization/tree/main).
- `ld_global`: Weight for global motion alignment ($\lambda_{g}$ in the paper). <i>Default `0.4`</i>

- `ld_local`: Weight for local motion refinement ($\lambda_{l}$ in the paper). <i>Default `0.2`</i>

- `num_levels`: Number of levels in discrete wavelet transform. <i>Default `2` for 8-frames input video, `3` for 16-frames input video</i>

- `ld_levels`: Weight for the alignment of each wavelet coefficients. <i>Default: `[1]*(num_levels+1)`</i>

## Citation
If you make use of our work, please cite our paper.
```bibtex
@article{park2024spectral,
  title={Spectral Motion Alignment for Video Motion Transfer using Diffusion Models},
  author={Park, Geon Yeong and Jeong, Hyeonho and Lee, Sang Wan and Ye, Jong Chul},
  journal={arXiv preprint arXiv:2403.15249},
  year={2024}
}
```

## Shoutouts
- SMA is validated on various open-source video/image diffusion models: [Show-1](https://huggingface.co/showlab/show-1-base), [Zeroscope-V2](https://huggingface.co/cerspense/zeroscope_v2_576w), [Stable Diffusion](https://huggingface.co/runwayml/stable-diffusion-v1-5), and [ControlNet](https://huggingface.co/lllyasviel/control_v11f1p_sd15_depth).
- SMA demonstrated its compatibility with four leading video-to-video frameworks: [VMC](https://arxiv.org/abs/2312.00845), [MotionDirector](https://arxiv.org/abs/2310.08465), [Tune-A-Video](https://arxiv.org/abs/2212.11565), [ControlVideo](https://arxiv.org/abs/2305.17098).
  

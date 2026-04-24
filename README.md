# screenshot-stitcher

[English](README.md) | [Chinese](README.zh-CN.md)

A small CLI for stitching multiple vertically scrolling iPhone screenshots into one long image.

It is designed for ordered screenshots from the same device and works best on list-like pages, app stores, settings screens, and similar vertical interfaces.

This is not an AI image generation tool. It is a deterministic image-processing utility powered by OpenCV and NumPy: it crops stable UI chrome, searches for overlapping regions, verifies alignment with visual features, and chooses a clean horizontal seam.

## Showcase

Full grouped sample assets live under [`examples/cases/`](examples/cases).

<table>
  <tr>
    <th align="left">Case</th>
    <th align="left">Inputs</th>
    <th align="left">Stitched Output</th>
  </tr>
  <tr>
    <td><strong>App Store Search</strong><br/>3 screenshots<br/><a href="examples/cases/app-store-search/stitched.png">Full result</a></td>
    <td><a href="examples/cases/app-store-search/preview-inputs.png"><img src="examples/cases/app-store-search/preview-inputs.png" width="360" alt="App Store input screenshots" /></a></td>
    <td><a href="examples/cases/app-store-search/stitched.png"><img src="examples/cases/app-store-search/preview-stitched.png" width="180" alt="App Store stitched output" /></a></td>
  </tr>
  <tr>
    <td><strong>Xiaohongshu Profile</strong><br/>3 screenshots<br/><a href="examples/cases/xiaohongshu-profile/stitched.png">Full result</a></td>
    <td><a href="examples/cases/xiaohongshu-profile/preview-inputs.png"><img src="examples/cases/xiaohongshu-profile/preview-inputs.png" width="360" alt="Xiaohongshu profile input screenshots" /></a></td>
    <td><a href="examples/cases/xiaohongshu-profile/stitched.png"><img src="examples/cases/xiaohongshu-profile/preview-stitched.png" width="180" alt="Xiaohongshu profile stitched output" /></a></td>
  </tr>
  <tr>
    <td><strong>Apple Homepage</strong><br/>5 screenshots<br/><a href="examples/cases/apple-homepage/stitched.png">Full result</a></td>
    <td><a href="examples/cases/apple-homepage/preview-inputs.png"><img src="examples/cases/apple-homepage/preview-inputs.png" width="360" alt="Apple homepage input screenshots" /></a></td>
    <td><a href="examples/cases/apple-homepage/stitched.png"><img src="examples/cases/apple-homepage/preview-stitched.png" width="180" alt="Apple homepage stitched output" /></a></td>
  </tr>
</table>

## Why Not Just Use GPT-Image-2?

Long screenshot stitching is mostly a structural alignment problem, not an image generation problem. A general image model can produce plausible-looking output, but it may duplicate browser chrome, repeat page sections, or blur seams that should stay exact.

The comparison below uses the same Apple homepage flow:

<table>
  <tr>
    <th align="left">screenshot-stitcher</th>
    <th align="left">GPT-image-2</th>
  </tr>
  <tr>
    <td><a href="examples/cases/apple-homepage/stitched.png"><img src="examples/comparisons/gpt-image-2/apple-homepage/screenshot-stitcher.png" width="180" alt="screenshot-stitcher Apple homepage result" /></a></td>
    <td><a href="examples/comparisons/gpt-image-2/apple-homepage/gpt-image-2.png"><img src="examples/comparisons/gpt-image-2/apple-homepage/gpt-image-2.png" width="180" alt="GPT-image-2 Apple homepage result" /></a></td>
  </tr>
</table>

## Features

- Stitch screenshots in the exact order you pass on the command line
- Detect overlap between adjacent screenshots and avoid duplicated content
- Choose a cleaner horizontal seam instead of blindly cutting and stacking
- Tune top/bottom UI cropping and horizontal edge masking with CLI flags
- Keep working with a fallback mode when overlap confidence is not strong enough

## Installation

Requirements:

- Python `3.10` or newer
- `pip`
- macOS, Linux, or Windows with prebuilt `opencv-python` wheels available
- `numpy`
- `opencv-python`

The package is meant to be installed with `pip`.

### From PyPI

Once the package is published to PyPI, this is the recommended install path:

```bash
pip install screenshot-stitcher
screenshot-stitcher --help
```

If your machine has multiple Python installations, use `python -m pip` to make sure you install into the environment you intend to use:

```bash
python -m pip install screenshot-stitcher
```

### From GitHub

If the package is not on PyPI yet, install directly from the public repository:

```bash
pip install "git+https://github.com/mate-matt/screenshot-stitcher.git"
screenshot-stitcher --help
```

### From A Cloned Checkout

If you are an agent such as Codex or Claude working inside a checked-out copy of this repo, install it from the repository root:

```bash
cd /path/to/screenshot-stitcher
pip install .
screenshot-stitcher --help
```

For editable local development:

```bash
pip install -e .
python main.py --help
```

To verify the example assets work after installation:

```bash
screenshot-stitcher \
  examples/cases/app-store-search/inputs/01.png \
  examples/cases/app-store-search/inputs/02.png \
  examples/cases/app-store-search/inputs/03.png \
  -o /tmp/app-store-search-stitched.png
```

## Usage

```bash
screenshot-stitcher img1.png img2.png img3.png -o output.png
```

You can also run it directly from the repo:

```bash
python main.py img1.png img2.png img3.png -o output.png
```

Common flags:

- `--top-crop`: override the default top crop
- `--bottom-crop`: override the default bottom crop
- `--no-navbar`: use only the status-bar height as the top crop
- `--no-tabbar`: use only the safe-area bottom as the bottom crop
- `--x-margin`: crop both left and right edges during matching, default `40`
- `--template-height`: template height used during overlap matching
- `--threshold`: confidence threshold for accepting overlap matches

## How It Works

`screenshot-stitcher` does not call GPT-image-2, an LLM, or any external vision API. The pipeline is local and OpenCV-driven:

- Convert screenshots to grayscale and edge representations with OpenCV
- Ignore configurable top/bottom UI chrome and noisy horizontal margins
- Estimate vertical overlap with multi-scale template and row-profile matching
- Re-score candidate matches with ORB feature support and local anchor consistency
- Pick a low-difference horizontal seam inside the overlap
- Stack the original image regions into one long screenshot

## Current Scope

This project is intentionally narrow:

- Same-device iPhone screenshots
- Vertical scrolling only
- Identical width across all inputs
- Input order is controlled by the user

## Known Limitations

- Repeated layouts can still confuse overlap matching
- Temporary overlays, badges, or floating UI can break otherwise valid overlaps
- Dynamic headers and browser bars may require tuning `--top-crop`, `--bottom-crop`, or `--x-margin`
- It is not a general panorama or arbitrary image stitching engine

## Codex Skill

This repo also includes a Codex skill at [`skills/screenshot-stitcher/`](skills/screenshot-stitcher) for routing screenshot stitching requests to the CLI and suggesting the most relevant flags.

Because the CLI contract is simple and the prompting surface is small, the same skill pattern can be integrated quickly into Claude, Codex, OpenClaw, Hermes, and similar agent-driven toolchains.

## Development

- `examples/cases/`: successful stitched outputs used in the README showcase
- `scripts/build_showcase_assets.py`: regenerates lightweight preview images for the showcase cases

## License

[MIT](LICENSE)

Runtime dependencies are installed from PyPI and are not vendored in this repository:

- NumPy: BSD 3-Clause
- opencv-python package scripts: MIT
- OpenCV: Apache 2.0

These are permissive licenses and are compatible with keeping this project under MIT. If you redistribute a bundled binary application instead of a normal PyPI package, include the relevant third-party notices for those bundled dependencies.

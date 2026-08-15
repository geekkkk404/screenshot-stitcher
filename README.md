# Screenshot Stitcher

A lightweight CLI tool for stitching vertically scrolling screenshots into one seamless image.

Automatically detects the correct order, finds overlapping regions, and cuts at clean seams for pixel-perfect results.

## Features

- **Auto order detection** — determines which screenshot goes first/second automatically
- **Overlap detection** — finds the exact overlap between consecutive screenshots
- **Clean seam cutting** — cuts at white background rows, never through text
- **Batch workflow** — drop screenshots into `input/`, run, get result in `output/`
- **Privacy-safe** — all processing happens locally, no data leaves your machine

## Quick Start

### 1. Setup

```bash
git clone https://github.com/YOUR_USERNAME/screenshot-stitcher.git
cd screenshot-stitcher
python -m venv .venv
.venv\Scripts\pip install opencv-python numpy
```

### 2. Usage

**Option A: Double-click**
- Put screenshots into `input/` folder
- Double-click `stitch.bat`
- Find result in `output/`

**Option B: Command line**
```bash
.venv\Scripts\python.exe stitch.py
```

### 3. Workflow

```
input/    →  Put your screenshots here
output/   →  Stitched result appears here
done/     →  Original screenshots move here after processing
```

## How It Works

1. **Order Detection** — tries all permutations of images, picks the one with best overlap correlation
2. **Overlap Detection** — slides images to find where they match (pixel correlation)
3. **Seam Selection** — finds the cleanest cut line (white background, no text)
4. **Stitching** — cuts and concatenates at the seam

## Requirements

- Python 3.10+
- opencv-python
- numpy

## License

MIT License - see [LICENSE](LICENSE) for details.

## Credits

Based on [mate-matt/screenshot-stitcher](https://github.com/mate-matt/screenshot-stitcher) (MIT License).

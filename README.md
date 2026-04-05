# paperDisplay

*AI-generated README*

A small, standalone e-ink pixel art display built on a Raspberry Pi Pico 2 and a Waveshare 2.66" B&W ePaper module. Displays pixel art images and animations with a matte, paper-like aesthetic.

**Author:** Linus Kelsey

---

## Hardware

| Component | Spec |
|---|---|
| Display | Waveshare 2.66" ePaper Module |
| Resolution | 296 × 152 px, black & white |
| Partial refresh | ~0.3s (used for animations) |
| Interface | SPI, 3.3V/5V, PH2.0 8-pin cable |
| Microcontroller | Raspberry Pi Pico 2 H (pre-soldered headers) |
| Connection | Jumper wires, no soldering required |
| Power (dev) | Micro-USB |
| Power (standalone, planned) | LiPo battery + TP4056 charging module |

---

## Project Structure

```
paperDisplay/
├── convert/
│   ├── convert.py          # Batch converts all media/ PNGs → pico/frames/ byte arrays
│   ├── convert_video.py    # Converts MP4/frames → byte arrays for animations (ffmpeg integrated)
│   └── filmstrip.py        # Stitches animation frames into a filmstrip PNG for QA
│
├── img_clean/
│   ├── convert_colour.py   # Converts colour pixel art → B&W PNGs, with interactive preview + tuning
│   ├── tune.py             # Parameter tuner for convert_colour.py (called automatically, or standalone)
│   ├── display.py          # Terminal image rendering helper (chafa / timg / kitten icat)
│   └── media/
│       ├── colour/         # Source colour PNGs go here
│       ├── bw/             # Converted B&W PNGs output here
│       └── preview/        # Side-by-side preview PNGs (generated with --preview flag)
│
├── media/
│   ├── img/                # Source B&W PNGs for static images
│   └── ani/                # Source B&W PNGs for animation frames, in folders by animation name
        └── <ani_name>      # Example animation
            ├── frames_raw  # Animation frames in .png format
            └── filmstrip/  # Filmstrip QA images output here
│
├── pico/
│   ├── main.py             # Entry point — runs on boot, displays first image found
│   ├── epd.py              # MicroPython SPI driver for the Waveshare 2.66" display
│   ├── deploy.py           # Syncs pico/ to the Pico over USB via mpremote
│   └── frames/
│       ├── img/            # Converted static image byte arrays
│       └── ani/            # Converted animation frame byte arrays
│
└── tools/
    └── frame-preview.html  # HTML animation viewer for .py Pico frames
```

***

## How It Works

The Pico runs MicroPython. On boot, `main.py` scans `pico/frames/img/` for byte array files, loads the first one it finds, and pushes it to the display via SPI. The display then sleeps — it holds the image indefinitely with zero power draw.

Animations use partial refresh mode (~0.3s per frame). After a configurable number of loop cycles, a full refresh clears any ghosting before resuming.

Pixel data is packed byte arrays where `0 = black`, `1 = white`, 8 pixels per byte. Each frame is `296 × 152 / 8 = 5,624 bytes`.

---

## Setup

### Prerequisites

**System packages:**

```bash
# ffmpeg — for MP4 frame extraction
brew install ffmpeg          # macOS
sudo apt install ffmpeg      # Linux

# Terminal image rendering (pick one; display.py tries them in order)
sudo apt install chafa       # Linux — works in any terminal
sudo apt install timg        # Linux — better quality
# kitten icat                # ships with Kitty / Ghostty terminals
```

**Python environment:**

```bash
python -m venv .venv
source .venv/bin/activate    # macOS/Linux
# .venv\Scripts\activate     # Windows

pip install -r requirements.txt
```

All commands below assume the venv is active. Use `python`, not `python3`.

**Pico deployment:**

```bash
pip install mpremote
```

Pico-side requires no extra packages — only MicroPython builtins (`machine`, `utime`, `os`, `framebuf`).

---

## Workflows

### Convert the entire media bank

Processes everything in `media/` in one command — MP4 extraction, stale frame wipe, and byte array conversion:

```bash
python convert/convert.py
```

This will:
1. Convert all PNGs in `media/img/` → `pico/frames/img/`
2. For each animation in `media/ani/`:
   - Auto-extract PNG frames from the MP4 if `frames_raw/` is empty
   - Wipe the output dir to clear stale frames from previous runs
   - Convert all frames → `pico/frames/ani/<name>/`

### Converting a colour image (interactive)

Run with `--preview` to get an inline terminal preview and optionally tune parameters per image:

```bash
python img_clean/convert_colour.py --preview
```

For each image this will:
1. Convert using current parameters (global defaults or per-image overrides)
2. Display a **side-by-side preview** — colour original left, B&W result right, with parameter values and pixel stats
3. Prompt: `Happy with this? [y / retune / q]`
   - `y` — accept and continue
   - `retune` — launch the parameter tuner
   - `q` — stop early

To batch convert without interaction:
```bash
python img_clean/convert_colour.py
```

Once happy, copy the B&W output from `img_clean/media/bw/` into `media/img/`, then run `python convert/convert.py`.

### Parameter tuning

Triggered by `retune` at the preview prompt. The tuner:
1. Runs a grid search over `uniformity_variance` values
2. Prints each variant inline so you can scroll to compare
3. Prompts: `Pick a variant [1-7]  (or 'q' to go back)`
4. Patches `PER_IMAGE_OVERRIDES` in `convert_colour.py` automatically with the chosen values
5. Re-converts and loops back to `Happy with this?`

Standalone usage:
```bash
python img_clean/tune.py img_clean/media/colour/<image.png>          # sweep uniformity_variance
python img_clean/tune.py img_clean/media/colour/<image.png> --full   # also sweep threshold + sharpen
python img_clean/tune.py img_clean/media/colour/<image.png> --uv 0 8 20 50  # specific values
```

#### Per-image overrides

Stored in `PER_IMAGE_OVERRIDES` at the top of `convert_colour.py`. Only values differing from global defaults are written:

```python
PER_IMAGE_OVERRIDES = {
    'spirited_away.png': {'uniformity_variance': 0},
    'totoro.png':        {'threshold': 120, 'sharpen_strength': 3.0},
}
```

#### Conversion pipeline

1. Greyscale conversion
2. Edge enhancement (sharpening)
3. Confident pixels → luminance threshold (Path A)
4. Ambiguous pixels near threshold → Floyd-Steinberg dithering (Path B)
5. Optional: uniform bright regions forced to white
6. Pad to 296 × 152 with white borders
7. Dithered fade on left/right padding only

#### Global default parameters

| Parameter | Default | Effect |
|---|---|---|
| `THRESHOLD` | `140` | Luminance cutoff — above → white, below → black |
| `MARGIN` | `40` | Confidence zone around threshold — ambiguous pixels go to dithering |
| `SHARPEN_STRENGTH` | `2.0` | Edge enhancement — `1.0` = none, `3.0+` = aggressive |
| `UNIFORMITY_VARIANCE` | `15` | Local variance below this → region forced to white. `0` = disabled |
| `UNIFORMITY_RADIUS` | `3` | Neighbourhood radius for variance calculation |

### QA — filmstrip preview

Before pushing an animation to the Pico, generate a filmstrip to inspect all frames at once:

```bash
python convert/filmstrip.py <animation_name>
# e.g. python convert/filmstrip.py twin_orb
```

Output: `media/filmstrip/<name>_filmstrip.png`

Also available as a browser-based frame-by-frame previewer — open `tools/frame-preview.html` in any browser and drop the `.py` frame files onto it. Supports playback, scrubbing, zoom, and FPS control.

### Adding a hand-drawn image

1. Draw at exactly **296 × 152 px** in Procreate using a single-pixel brush, export as PNG
2. Drop into `media/img/`
3. Run `python convert/convert.py`
4. Copy the resulting `.py` from `pico/frames/img/` onto the Pico — it will be picked up on next boot

---

## Pico Setup (first time)

1. Flash MicroPython onto the Pico 2 — hold BOOTSEL, connect USB, drag the MicroPython `.uf2` onto the drive
2. Open [Thonny](https://thonny.org) and connect to the Pico
3. Copy `pico/epd.py`, `pico/main.py`, and the `pico/frames/` directory onto the Pico filesystem
4. Confirm pin numbers at the top of `epd.py` match your wiring (see below)
5. Reboot — `main.py` runs automatically on boot

Once `mpremote` is installed, use `deploy.py` for faster iteration:
```bash
python pico/deploy.py                # full sync + reboot
python pico/deploy.py --frames-only  # push new frames only
python pico/deploy.py --dry-run      # preview what would be copied
```

### Wiring

```python
PIN_SCK  = 10   # SPI clock
PIN_MOSI = 11   # SPI data
PIN_CS   = 9    # Chip select
PIN_DC   = 8    # Data/command
PIN_RST  = 12   # Reset
PIN_BUSY = 13   # Busy
```

---

## Planned

**Software pipeline**
- Universal input formats — accept jpg, gif, webp etc., not just PNG
- GIF animation support alongside MP4
- Per-animation FPS metadata — extracted from source file, stored alongside frames
- Colour images auto-routed through `convert_colour.py` without manual pre-processing
- `--force` flag to re-extract MP4 frames even if `frames_raw/` is already populated

**Hardware extensions**
- `deploy.py` — push frames to Pico over USB in one command
- Button support in `main.py` — one button for image/animation mode, one to cycle content
- Standalone portable power via LiPo + TP4056
- Custom enclosure

**Universalisation**
- `devices.py` — config file with width, height, colour mode per Waveshare display
- `--device` flag on `convert.py` so all dimensions derive from a single source
- `epd.py` imports from the same device config
- `manifest.json` — generated by `convert.py`, lists all animations for dynamic discovery in `main.py`

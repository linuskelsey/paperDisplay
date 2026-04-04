# paperDisplay

*AI-generated README*

A small, standalone e-ink pixel art display built on a Raspberry Pi Pico 2 and a Waveshare 2.66" B&W ePaper module. Displays pixel art images and animations with a matte, paper-like aesthetic.

**Author:** Linus Kelsey

***

## Hardware

| Component | Spec |
|---|---|
| Display | Waveshare 2.66" ePaper Module |
| Resolution | 296 × 152 px, black & white |
| Partial refresh | 0.3s (used for animations) |
| Interface | SPI, 3.3V/5V, PH2.0 8-pin cable |
| Microcontroller | Raspberry Pi Pico 2 H (pre-soldered headers) |
| Connection | Jumper wires, no soldering required |
| Power (dev) | Micro-USB |
| Power (standalone, planned) | LiPo battery + TP4056 charging module |

***

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
│   ├── ani/                # Source B&W PNGs for animation frames, in folders by animation name
│   └── filmstrip/          # Filmstrip QA images output here
│
└── pico/
    ├── main.py             # Entry point — runs on boot, displays first image found
    ├── epd.py              # MicroPython SPI driver for the Waveshare 2.66" display
    ├── deploy.py           # Syncs pico/ to the Pico over USB via mpremote
    └── frames/
        ├── img/            # Converted static image byte arrays
        └── ani/            # Converted animation frame byte arrays
```

***

## How It Works

The Pico runs MicroPython. On boot, `main.py` scans `pico/frames/img/` for byte array files, loads the first one it finds, pushes it to the display via SPI, then puts the display to sleep. The display holds the image indefinitely with no power draw.

Pixel data is stored as packed byte arrays where `0 = black` and `1 = white`, with 8 pixels per byte. Each frame file is `296 × 152 / 8 = 5,624 bytes`.

***

## Workflows

### Converting a colour pixel art image (interactive)

The main conversion workflow. Run with `--preview` to get an inline terminal preview after each image and optionally retune parameters before moving on.

```bash
python3 convert/convert_colour.py --preview
```

For each image this will:
1. Convert using the current parameters (global defaults or any per-image overrides)
2. Display a **side-by-side preview** inline in the terminal — colour original on the left, B&W result on the right, with parameter values and pixel stats in a label bar
3. Prompt: `Happy with this? [y / retune / q]`
   - `y` — accept and move to the next image
   - `retune` — launch the parameter tuner (see below)
   - `q` — stop the run early

To batch convert without interaction:
```bash
python3 convert/convert_colour.py
```

### Parameter tuning

Triggered by typing `retune` at the "Happy with this?" prompt. The tuner:
1. Runs a grid search over `uniformity_variance` values (the most impactful parameter for most images)
2. Prints each variant **inline in the terminal**, one by one, so you can scroll up to compare
3. Prompts: `Pick a variant [1-7]  (or 'q' to go back)`
4. On picking a number, automatically patches `PER_IMAGE_OVERRIDES` in `convert_colour.py` with the chosen values
5. Re-converts the image and shows the updated preview
6. Loops back to `Happy with this?` — retune again if needed, or accept and move on

To also sweep `threshold` and `sharpen_strength` (slower):
```bash
# Standalone usage
python3 convert/tune.py img_clean/media/colour/<image.png> --full
```

To try specific `uniformity_variance` values instead of the default sweep:
```bash
python3 convert/tune.py img_clean/media/colour/<image.png> --uv 0 8 20 50
```

#### Per-image overrides

Tuned parameters are stored in `PER_IMAGE_OVERRIDES` at the top of `convert_colour.py`. Only values that differ from the global defaults are written — the dict stays minimal. You can also edit it manually:

```python
PER_IMAGE_OVERRIDES = {
    'spirited_away.png': {'uniformity_variance': 0},
    'totoro.png':        {'threshold': 120, 'sharpen_strength': 3.0},
}
```

#### Conversion pipeline

Each image goes through:
1. Greyscale conversion
2. Edge enhancement (sharpening)
3. Confident pixels → luminance threshold (Path A)
4. Ambiguous pixels near the threshold → Floyd-Steinberg dithering (Path B)
5. Optional: uniform bright regions (e.g. skies) forced to white
6. Pad to 296 × 152 with white borders
7. Dithered fade applied to left/right padding

#### Global default parameters

| Parameter | Default | Effect |
|---|---|---|
| `THRESHOLD` | `140` | Luminance cutoff — pixels above go white, below go black |
| `MARGIN` | `40` | Confidence zone around threshold — ambiguous pixels go to dithering |
| `SHARPEN_STRENGTH` | `2.0` | Edge enhancement — `1.0` = none, `3.0+` = aggressive |
| `UNIFORMITY_VARIANCE` | `15` | Local variance below this → uniform region forced to white. `0` = disabled |
| `UNIFORMITY_RADIUS` | `3` | Neighbourhood radius for variance calculation |

### Adding a new hand-drawn image

1. Draw at exactly **296 × 152 px** in Procreate using a single-pixel brush
2. Export as PNG into `media/img/`
3. Run the converter from the project root:
   ```bash
   python3 convert/convert.py
   ```
4. Copy the resulting `.py` file from `pico/frames/img/` onto the Pico
5. Reboot — it will be picked up automatically

### Adding a new animation

From an MP4 (ffmpeg extraction is handled automatically):
```bash
python3 convert/convert_video.py media/ani/<name>/<name>.mp4 pico/frames/ani/<name> <name>
```

From a pre-extracted frames folder:
```bash
python3 convert/convert_video.py media/ani/<name>/frames_raw pico/frames/ani/<name> <name>
```

Optional flags:
```bash
--fps 12          # extract at 12 fps (default: 10)
--start 2.5       # start time in seconds
--end 8.0         # end time in seconds
```

To QA an animation before pushing to the Pico, generate a filmstrip:
```bash
python3 convert/filmstrip.py <animation_name>
# e.g. python3 convert/filmstrip.py twin_orb
```
Output goes to `media/filmstrip/<name>_filmstrip.png`.

***

## Pico Setup (first time)

1. Flash MicroPython onto the Pico 2 — hold BOOTSEL, connect USB, drag and drop the MicroPython `.uf2` file
2. Open [Thonny](https://thonny.org) and connect to the Pico
3. Copy `pico/epd.py`, `pico/main.py`, and the `pico/frames/` directory onto the Pico's filesystem
4. Confirm pin numbers at the top of `epd.py` match your wiring (see below)
5. Reboot — `main.py` runs automatically on boot

Once `mpremote` is installed, use `deploy.py` instead of Thonny for faster iteration:
```bash
python3 pico/deploy.py              # full sync + reboot
python3 pico/deploy.py --frames-only  # push new frames only (faster)
python3 pico/deploy.py --dry-run    # preview what would be copied
```

### Wiring (jumper wires, no soldering)

Confirm GPIO pin assignments in `epd.py` before first boot:

```python
PIN_SCK  = 10   # SPI clock
PIN_MOSI = 11   # SPI data
PIN_CS   = 9    # Chip select
PIN_DC   = 8    # Data/command
PIN_RST  = 12   # Reset
PIN_BUSY = 13   # Busy
```

***

## Dependencies

Python (laptop-side):

```bash
pip install Pillow numpy scipy
```

For terminal image previews — `chafa` is the most broadly compatible option:
```bash
sudo apt install chafa       # Linux — works in any terminal
sudo apt install timg        # Linux alternative with better quality
# kitten icat                # ships with Kitty terminal; also works in Ghostty
```
`display.py` tries `kitten icat` → `timg` → `chafa` → external open, in that order.

For animation import from MP4:
```bash
sudo apt install ffmpeg      # Linux
brew install ffmpeg          # macOS
```

For deploying to the Pico:
```bash
pip install mpremote
```

Pico-side — no dependencies beyond MicroPython builtins (`machine`, `utime`, `os`, `framebuf`).

***

## Planned

- Button support — one button to toggle image/animation mode, one to cycle through content
- Animation playback via partial refresh
- Standalone portable power via LiPo + TP4056
- Custom enclosure

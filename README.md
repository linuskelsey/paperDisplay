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
| Partial refresh | 0.3s (used for animations) |
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
│   └── convert_video.py    # Extracts MP4 frames → byte arrays for animations
│
├── img_clean/
│   ├── convert_colour.py   # Converts colour pixel art → B&W PNGs for Procreate touch-up
│   └── media/
│       ├── colour/         # Source colour PNGs go here
│       └── bw/             # Converted B&W PNGs output here
│
├── media/
│   ├── img/                # Source B&W PNGs for static images
│   └── ani/                # Source BW PNGs for frames of animations, in folders labeled by animation

│
└── pico/
    ├── main.py             # Entry point — runs on boot, displays first image found
    ├── epd.py              # MicroPython SPI driver for the Waveshare 2.66" display
    └── frames/
        ├── img/            # Converted static image byte arrays
        └── ani/            # Converted frame image byte arrays
```

---

## How It Works

The Pico runs MicroPython. On boot, `main.py` scans `pico/frames/img/` for byte array files, loads the first one it finds, pushes it to the display via SPI, then puts the display to sleep. The display holds the image indefinitely with no power draw.

Pixel data is stored as packed byte arrays where `0 = black` and `1 = white`, with 8 pixels per byte. Each frame file is `296 × 152 / 8 = 5,624 bytes`.

---

## Workflows

### Adding a new hand-drawn image

1. Draw at exactly **296 × 152 px** in Procreate using a single-pixel brush
2. Export as PNG into `media/img/`
3. Run the converter from the project root:
   ```bash
   python3 convert/convert.py
   ```
4. Copy the resulting `.py` file from `pico/frames/img/` onto the Pico
5. Reboot — it will be picked up automatically

### Converting a colour pixel art image

1. Drop the colour PNG into `img_clean/media/colour/`
2. Run from anywhere:
   ```bash
   python3 img_clean/convert_colour.py
   ```
3. Retrieve the `_bw.png` output from `img_clean/media/bw/`
4. Touch up in Procreate as needed
5. Export the finished PNG into `media/img/` and run `convert/convert.py`

The colour converter uses a combined luminance threshold + Floyd-Steinberg dithering pipeline with edge enhancement, and applies a dithered fade on the left and right borders. Per-image parameter overrides are available at the top of `convert_colour.py`.

### Adding a new animation

1. Place the source MP4 in `media/ani/<animation_name>/`
2. Extract frames using ffmpeg:
   ```bash
   ffmpeg -i media/ani/<name>/<name>.mp4 media/ani/<name>/frames_raw/frame_%03d.png
   ```
3. Run the converter:
   ```bash
   python3 convert/convert.py
   ```
4. Copy the resulting `pico/frames/ani/<name>/` folder onto the Pico

---

## Pico Setup (first time)

1. Flash MicroPython onto the Pico 2 — hold BOOTSEL, connect USB, drag and drop the MicroPython `.uf2` file
2. Open [Thonny](https://thonny.org) and connect to the Pico
3. Copy `pico/epd.py`, `pico/main.py`, and the `pico/frames/` directory onto the Pico's filesystem
4. Confirm pin numbers at the top of `epd.py` match your wiring (see below)
5. Reboot — `main.py` runs automatically on boot

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

---

## Dependencies

Python (laptop-side scripts):

```bash
pip install Pillow numpy scipy
```

Pico-side — no dependencies beyond MicroPython builtins (`machine`, `utime`, `os`, `framebuf`).

---

## Planned

- Button support — one button to toggle image/animation mode, one to cycle through content
- Animation playback via partial refresh
- Per-image automatic parameter analysis for the colour converter
- Standalone portable power via LiPo + TP4056
- Custom enclosure

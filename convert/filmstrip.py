#!/usr/bin/env python3
"""
filmstrip.py
Visual QA tool — stitches converted animation frames into a filmstrip PNG
so all frames can be inspected at a glance before deploying to the Pico.
 
Reads from pico/frames/ani/<name>/ (byte array .py files produced by
convert.py or convert_video.py) and reconstructs each frame back into a
greyscale image for layout into a contact-sheet grid.
 
Output: media/ani/<name>/filmstrip/<name>_filmstrip.png
 
Usage:
    python convert/filmstrip.py <animation_name>
    python convert/filmstrip.py totoro
    python convert/filmstrip.py totoro --cols 8
    python convert/filmstrip.py totoro --out /path/to/output.png
"""

import os
import sys
import re
import ast
import argparse
import numpy as np
from PIL import Image, ImageDraw, ImageFont

DISPLAY_WIDTH  = 296
DISPLAY_HEIGHT = 152
DEFAULT_COLS   = 10
LABEL_H        = 20
BORDER         = 2
LABEL_BG       = (30, 30, 30)

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR    = os.path.dirname(BASE_DIR)
FRAMES_BASE = os.path.join(ROOT_DIR, 'pico', 'frames', 'ani')
MEDIA_ANI   = os.path.join(ROOT_DIR, 'media', 'ani')

# Matches auto-generated frame files: <name>_001.py etc.
FRAME_FILE_RE = re.compile(r'^.+_\d+\.py$')


# ---------------------------------------------------------------------------
# Byte array loading
# ---------------------------------------------------------------------------

def load_frame_py(path):
    """Parse a frame .py file and return a greyscale PIL Image."""
    with open(path, 'r') as f:
        source = f.read()

    # Extract WIDTH and HEIGHT if present, fall back to display defaults
    w_match = re.search(r'^WIDTH\s*=\s*(\d+)', source, re.MULTILINE)
    h_match = re.search(r'^HEIGHT\s*=\s*(\d+)', source, re.MULTILINE)
    w = int(w_match.group(1)) if w_match else DISPLAY_WIDTH
    h = int(h_match.group(1)) if h_match else DISPLAY_HEIGHT

    # Find the bytearray literal
    ba_match = re.search(r'bytearray\(\[([^\]]+)\]', source, re.DOTALL)
    if not ba_match:
        raise ValueError(f"Could not find bytearray in {path}")

    data = bytes(int(x.strip(), 16) for x in ba_match.group(1).split(',') if x.strip())
    return bytes_to_image(data, w, h)


def bytes_to_image(data, w, h):
    """Unpack 1bpp byte array into a greyscale PIL Image."""
    arr = np.zeros((h, w), dtype=np.uint8)
    idx = 0
    for y in range(h):
        for x in range(0, w, 8):
            if idx >= len(data):
                break
            byte = data[idx]
            idx += 1
            for bit in range(8):
                if x + bit < w:
                    arr[y, x + bit] = 255 if (byte >> (7 - bit)) & 1 else 0
    return Image.fromarray(arr, mode='L')


# ---------------------------------------------------------------------------
# Filmstrip builder
# ---------------------------------------------------------------------------

def build_filmstrip(frames_dir, name, cols, output_path):
    py_files = sorted([
        os.path.join(frames_dir, f)
        for f in os.listdir(frames_dir)
        if FRAME_FILE_RE.match(f)   # only frame_XXXXX.py files
    ])

    if not py_files:
        print(f"No frame .py files found in {frames_dir}")
        sys.exit(1)

    n    = len(py_files)
    rows = (n + cols - 1) // cols
    tw   = DISPLAY_WIDTH
    th   = DISPLAY_HEIGHT

    sheet_w = cols * (tw + BORDER) + BORDER
    sheet_h = rows * (th + LABEL_H + BORDER) + BORDER
    sheet   = Image.new('RGB', (sheet_w, sheet_h), (10, 10, 10))
    draw    = ImageDraw.Draw(sheet)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 10)
    except Exception:
        font = ImageFont.load_default()

    print(f"  Building filmstrip: {n} frames, {cols} per row ({rows} rows)...")

    fps_hint = 3.0

    for idx, py_path in enumerate(py_files):
        col = idx % cols
        row = idx // cols
        x   = BORDER + col * (tw + BORDER)
        y   = BORDER + row * (th + LABEL_H + BORDER)

        try:
            img = load_frame_py(py_path)
        except Exception as e:
            print(f"  Warning: could not load {os.path.basename(py_path)}: {e}")
            img = Image.new('L', (DISPLAY_WIDTH, DISPLAY_HEIGHT), 64)

        sheet.paste(img.convert('RGB'), (x, y))

        label_y = y + th
        draw.rectangle([(x, label_y), (x + tw, label_y + LABEL_H)], fill=LABEL_BG)
        frame_num = idx + 1
        timestamp = frame_num / fps_hint
        label     = f"#{frame_num:03d}  {timestamp:.1f}s"
        draw.text((x + 3, label_y + 4), label, fill=(220, 200, 140), font=font)

        if (idx + 1) % 50 == 0 or (idx + 1) == n:
            print(f"  [{idx+1}/{n}]")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    sheet.save(output_path)
    rel = os.path.relpath(output_path, ROOT_DIR)
    print(f"\n  Filmstrip saved -> {rel}")
    print(f"  {sheet_w}x{sheet_h}px  |  {n} frames  |  ~{n/fps_hint:.1f}s at 3fps")
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description='Build a filmstrip QA image from Pico animation frames.'
    )
    parser.add_argument('name', help='Animation name (folder under pico/frames/ani/)')
    parser.add_argument('--cols', type=int, default=DEFAULT_COLS,
                        help=f'Frames per row (default: {DEFAULT_COLS})')
    parser.add_argument('--out', metavar='PATH',
                        help='Output path (default: media/ani/<name>/filmstrip/<name>_filmstrip.png)')
    args = parser.parse_args()

    frames_dir = os.path.join(FRAMES_BASE, args.name)
    if not os.path.isdir(frames_dir):
        print(f"Animation not found: {frames_dir}")
        sys.exit(1)

    output_path = args.out or os.path.join(
        ROOT_DIR, 'media', 'ani', args.name, 'filmstrip', f"{args.name}_filmstrip.png"
    )
    build_filmstrip(frames_dir, args.name, args.cols, output_path)


if __name__ == '__main__':
    main()

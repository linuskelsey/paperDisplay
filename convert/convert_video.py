#!/usr/bin/env python3
"""
convert_video.py
Converts a video file (or folder of pre-extracted image frames) into packed
1-bit byte array .py files ready to copy onto the Pico.
 
Byte convention: 0 = black, 1 = white. 8 pixels per byte, MSB first.
Frames are stored at the display's native 296 × 152 px (landscape). Unlike
static images converted by convert.py, video frames are not rotated — they
are composited onto a black canvas at native size and centred.
 
Full pipeline:
    video → ffmpeg → frames_raw PNGs → 1-bit byte array .py files
 
Usage:
    python convert/convert_video.py media/ani/totoro/totoro.mp4 totoro
    python convert/convert_video.py media/ani/totoro/frames_raw totoro  # pre-extracted frames
    python convert/convert_video.py media/ani/totoro/totoro.mp4 totoro --fps 10
    python convert/convert_video.py media/ani/totoro/totoro.mp4 totoro --start 2.0 --end 8.5
    python convert/convert_video.py media/ani/totoro/totoro.mp4 totoro --no-dither
"""

import os
import sys
import re
import shutil
import argparse
import subprocess
import numpy as np
from PIL import Image, ImageFilter

DISPLAY_WIDTH  = 296
DISPLAY_HEIGHT = 152
DEFAULT_FPS    = 3   # matches e-ink partial refresh rate (~0.3s/frame)

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR    = os.path.dirname(BASE_DIR)
FRAMES_BASE = os.path.join(ROOT_DIR, 'pico', 'frames', 'ani')
MEDIA_ANI   = os.path.join(ROOT_DIR, 'media', 'ani')


# ---------------------------------------------------------------------------
# Frame extraction
# ---------------------------------------------------------------------------

def extract_frames_ffmpeg(input_path, out_dir, fps, start=None, end=None):
    """Extract frames from a video file using ffmpeg."""
    if not shutil.which('ffmpeg'):
        print("Error: ffmpeg not found. Install it with: sudo apt install ffmpeg")
        sys.exit(1)

    cmd = ['ffmpeg', '-y']
    if start is not None:
        cmd += ['-ss', str(start)]
    cmd += ['-i', input_path]
    if end is not None:
        duration = end - (start or 0)
        cmd += ['-t', str(duration)]
    cmd += [
        '-vf', f'fps={fps}',
        '-vsync', 'vfr',       # prevents duplicate frames at clip boundaries
        '-q:v', '2',
        os.path.join(out_dir, 'frame_%05d.png')
    ]

    print(f"  Extracting frames at {fps}fps...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ffmpeg error:\n{result.stderr}")
        sys.exit(1)


def collect_frames(source):
    """Return sorted image paths from a directory. PNG/JPG/JPEG/BMP/WEBP only."""
    exts = {'.png', '.jpg', '.jpeg', '.bmp', '.webp'}
    files = sorted([
        os.path.join(source, f) for f in os.listdir(source)
        if os.path.splitext(f)[1].lower() in exts
    ])
    return files


# ---------------------------------------------------------------------------
# Image pipeline — no upscaling, native size centred on black canvas
# ---------------------------------------------------------------------------

def frame_to_bw(img_path, dither=True):
    """
    Convert one frame to a 296x152 1-bit PIL Image.
    Source frame is pasted at native size, centred on a black canvas.
    No upscaling — preserves pixel art integrity.
    """
    img  = Image.open(img_path).convert('L')
    src_w, src_h = img.size

    # Only scale DOWN if the source is larger than the display
    if src_w > DISPLAY_WIDTH or src_h > DISPLAY_HEIGHT:
        scale = min(DISPLAY_WIDTH / src_w, DISPLAY_HEIGHT / src_h)
        new_w = int(src_w * scale)
        new_h = int(src_h * scale)
        img   = img.resize((new_w, new_h), Image.LANCZOS)

    if dither:
        bw = img.convert('1', dither=Image.Dither.FLOYDSTEINBERG)
    else:
        bw = img.point(lambda p: 255 if p >= 140 else 0, '1')

    # Black canvas — matches original behaviour for pixel art
    canvas   = Image.new('1', (DISPLAY_WIDTH, DISPLAY_HEIGHT), 0)
    offset_x = (DISPLAY_WIDTH  - img.width)  // 2
    offset_y = (DISPLAY_HEIGHT - img.height) // 2
    canvas.paste(bw, (offset_x, offset_y))
    return canvas


# ---------------------------------------------------------------------------
# Byte array packing
# ---------------------------------------------------------------------------

def image_to_byte_array(bw_img, var_name):
    """
    Pack a 1-bit PIL Image into a Python bytearray string.
    Convention: 0 = black, 1 = white (matches convert.py and epd.py).
    """
    pixels   = bw_img.load()
    w, h     = bw_img.size
    num_bytes = (w * h) // 8
    buf       = bytearray(num_bytes)

    for y in range(h):
        for x in range(w):
            if pixels[x, y] == 255:
                byte_index = (y * w + x) // 8
                bit_index  = 7 - ((y * w + x) % 8)
                buf[byte_index] |= (1 << bit_index)

    hex_values = [f'0x{b:02X}' for b in buf]
    hex_rows   = [
        '    ' + ', '.join(hex_values[i:i+16])
        for i in range(0, len(hex_values), 16)
    ]
    content = (
        f"# Auto-generated by convert_video.py\n"
        f"# {w}x{h} pixels, 1-bit black and white\n\n"
        f"WIDTH = {w}\n"
        f"HEIGHT = {h}\n\n"
        f"{var_name} = bytearray([\n"
        + ',\n'.join(hex_rows)
        + f"\n])\n"
    )
    return content


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def convert(source, name, fps=DEFAULT_FPS, start=None, end=None, dither=True):
    frames_raw_dir = os.path.join(MEDIA_ANI, name, 'frames_raw')
    pico_out_dir   = os.path.join(FRAMES_BASE, name)

    if os.path.isfile(source):
        # Video file — extract to frames_raw
        os.makedirs(frames_raw_dir, exist_ok=True)
        # Clear any existing frames_raw to avoid stale frames
        for f in os.listdir(frames_raw_dir):
            if f.lower().endswith('.png'):
                os.remove(os.path.join(frames_raw_dir, f))
        extract_frames_ffmpeg(source, frames_raw_dir, fps, start=start, end=end)
        frame_paths = collect_frames(frames_raw_dir)
    elif os.path.isdir(source):
        # Pre-extracted frames folder
        frame_paths = collect_frames(source)
    else:
        print(f"Error: {source} is not a file or directory.")
        sys.exit(1)

    if not frame_paths:
        print(f"No image frames found in source.")
        sys.exit(1)

    print(f"  Found {len(frame_paths)} frame(s) — converting...")

    # Wipe and recreate pico output dir entirely
    if os.path.isdir(pico_out_dir):
        shutil.rmtree(pico_out_dir)
    os.makedirs(pico_out_dir, exist_ok=True)

    for i, frame_path in enumerate(frame_paths, 1):
        bw       = frame_to_bw(frame_path, dither=dither)
        var_name = f"frame_{i:05d}"
        content  = image_to_byte_array(bw, var_name)
        out_path = os.path.join(pico_out_dir, f"{var_name}.py")
        with open(out_path, 'w') as f:
            f.write(content)

        if i % 10 == 0 or i == len(frame_paths):
            print(f"  [{i}/{len(frame_paths)}] {var_name}.py")

    print(f"\n  Done — {len(frame_paths)} frames")
    print(f"  Raw frames -> media/ani/{name}/frames_raw/")
    print(f"  Byte arrays -> pico/frames/ani/{name}/")
    return pico_out_dir, len(frame_paths)


def main():
    parser = argparse.ArgumentParser(
        description='Convert a video or image frames to Pico byte array files.'
    )
    parser.add_argument('source',
                        help='Path to a video file or a directory of image frames')
    parser.add_argument('name',
                        help='Animation name — used as the output folder name')
    parser.add_argument('--fps', type=float, default=DEFAULT_FPS,
                        help=f'Frame rate for extraction (default: {DEFAULT_FPS})')
    parser.add_argument('--start', type=float, default=None,
                        help='Start time in seconds (video only)')
    parser.add_argument('--end', type=float, default=None,
                        help='End time in seconds (video only)')
    parser.add_argument('--no-dither', action='store_true',
                        help='Use threshold instead of Floyd-Steinberg dithering')
    args = parser.parse_args()

    print(f"Converting '{args.name}' from {args.source}\n")
    convert(
        args.source, args.name,
        fps=args.fps,
        start=args.start,
        end=args.end,
        dither=not args.no_dither,
    )


if __name__ == '__main__':
    main()

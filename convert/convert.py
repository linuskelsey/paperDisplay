#!/usr/bin/env python3
"""
convert.py
Batch converts all media/ images and animations to MicroPython byte arrays,
ready to copy onto the Pico.
 
Orientation note:
    The Waveshare 2.66" display is natively portrait (152 × 296 px). The device
    is mounted landscape, so every source image is rotated 90° clockwise here
    before packing. Draw and export pixel art at 296 × 152 px — the rotation is
    applied automatically.
 
Byte convention: 0 = black, 1 = white. 8 pixels per byte, MSB first.
Each packed frame is 152 × 296 / 8 = 5,624 bytes.
 
Input structure:
    media/
    ├── img/                        ← B&W source PNGs (296 × 152 px)
    │   └── totoro.png
    └── ani/                        ← animations, one subfolder per clip
        └── twin_orb/
            ├── twin_orb.mp4        ← optional: frames auto-extracted via ffmpeg
            └── frames_raw/         ← raw PNG frames (auto-populated or pre-placed)
                ├── frame_0001.png
                └── ...
 
Output structure:
    pico/frames/
    ├── img/
    │   └── totoro.py
    └── ani/
        └── twin_orb/
            ├── twin_orb_001.py
            └── ...
 
Usage:
    python convert/convert.py       (from anywhere in the project)
"""

import os
import sys
import shutil
import subprocess
from PIL import Image

# Display dimensions
WIDTH  = 296
HEIGHT = 152
DISPLAY_FPS = 3   # Waveshare 2.66" partial refresh ~0.3s/frame

# Paths — anchored to project root (one level up from this script)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR   = os.path.dirname(SCRIPT_DIR)
MEDIA_DIR  = os.path.join(ROOT_DIR, 'media')
IMG_DIR    = os.path.join(MEDIA_DIR, 'img')
ANI_DIR    = os.path.join(MEDIA_DIR, 'ani')
FRAMES_DIR = os.path.join(ROOT_DIR, 'pico', 'frames')
FRAMES_IMG = os.path.join(FRAMES_DIR, 'img')
FRAMES_ANI = os.path.join(FRAMES_DIR, 'ani')


def png_to_bytearray(input_path):
    """Convert a PNG to a packed byte array. 0 = black, 1 = white."""
    img = Image.open(input_path)
    img = img.rotate(90, expand=True)
    if img.size != (HEIGHT, WIDTH):
        img = img.resize((HEIGHT, WIDTH), Image.LANCZOS)
    img = img.convert('1')
    pixels = list(img.getdata())

    byte_array = []
    for i in range(0, len(pixels), 8):
        byte = 0
        for bit in range(8):
            if i + bit < len(pixels):
                pixel = 1 if pixels[i + bit] == 255 else 0
                byte = (byte << 1) | pixel
        byte_array.append(byte)
    return byte_array


def write_py(byte_array, output_path, name, source_path):
    """Write a byte array to a .py file."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(f"# Auto-generated from {os.path.relpath(source_path, ROOT_DIR)}\n")
        f.write(f"# {WIDTH}x{HEIGHT} pixels, 1-bit black and white\n\n")
        f.write(f"# Image is rotated 90° — stored in portrait (152×296) orientation for landscape display\n")
        f.write(f"{name} = bytearray([\n    ")
        for i, b in enumerate(byte_array):
            f.write(f"0x{b:02X},")
            if (i + 1) % 16 == 0:
                f.write("\n    ")
            else:
                f.write(" ")
        f.write("\n])\n")


def convert_images():
    """Convert all PNGs in media/img/ → pico/frames/img/"""
    if not os.path.isdir(IMG_DIR):
        print("  No media/img/ folder found, skipping static images.")
        return

    files = sorted([f for f in os.listdir(IMG_DIR) if f.lower().endswith('.png')])
    if not files:
        print("  No PNGs found in media/img/")
        return

    print(f"  Found {len(files)} static image(s)...")
    for filename in files:
        input_path  = os.path.join(IMG_DIR, filename)
        name        = os.path.splitext(filename)[0]
        output_path = os.path.join(FRAMES_IMG, f"{name}.py")

        byte_array = png_to_bytearray(input_path)
        write_py(byte_array, output_path, name, input_path)
        print(f"    {filename} → pico/frames/img/{name}.py  ({len(byte_array)} bytes)")


def convert_animations():
    """Convert all animation folders in media/ani/ → pico/frames/ani/<name>/"""
    if not os.path.isdir(ANI_DIR):
        print("  No media/ani/ folder found, skipping animations.")
        return

    ani_folders = sorted([
        d for d in os.listdir(ANI_DIR)
        if os.path.isdir(os.path.join(ANI_DIR, d))
    ])
    if not ani_folders:
        print("  No animation folders found in media/ani/")
        return

    for ani_name in ani_folders:
        frames_raw = os.path.join(ANI_DIR, ani_name, 'frames_raw')

        # Auto-extract frames from MP4 if frames_raw/ is empty or missing
        mp4_path = os.path.join(ANI_DIR, ani_name, f"{ani_name}.mp4")
        if os.path.exists(mp4_path):
            print(f"  {ani_name}: extracting frames from MP4...")
            os.makedirs(frames_raw, exist_ok=True)
            for f in os.listdir(frames_raw):
                if f.lower().endswith('.png'):
                    os.remove(os.path.join(frames_raw, f))
            subprocess.run([
                'ffmpeg', '-i', mp4_path,
                '-vf', f'fps={DISPLAY_FPS}',
                '-vsync', 'vfr',
                os.path.join(frames_raw, f'{ani_name}_%03d.png'),
                '-loglevel', 'error'
            ], check=True)

        if not os.path.isdir(frames_raw):
            print(f"  Skipping {ani_name}/ — no frames_raw/ subfolder found.")
            continue

        files = sorted([f for f in os.listdir(frames_raw) if f.lower().endswith('.png')])
        if not files:
            print(f"  Skipping {ani_name}/ — no PNGs in frames_raw/")
            continue

        output_dir = os.path.join(FRAMES_ANI, ani_name)

        # Wipe output dir to clear stale frames from previous runs
        if os.path.isdir(output_dir):
            shutil.rmtree(output_dir)
        os.makedirs(output_dir, exist_ok=True)

        print(f"  {ani_name}: {len(files)} frame(s)...")

        for i, filename in enumerate(files, start=1):
            input_path  = os.path.join(frames_raw, filename)
            var_name    = f"{ani_name}_{i:03d}"
            output_path = os.path.join(output_dir, f"{var_name}.py")

            byte_array = png_to_bytearray(input_path)
            write_py(byte_array, output_path, var_name, input_path)

        print(f"    → pico/frames/ani/{ani_name}/  ({len(files)} files)")


def main():
    print("Converting static images...")
    convert_images()
    print("\nConverting animations...")
    convert_animations()
    print("\nAll done.")


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Convert a PNG image to a MicroPython byte array for the Waveshare 2.66" e-ink display.
Output: a .py file containing a byte array ready to import on the Pico.

Usage:
    python3 convert.py <input.png> <output.py> <name>

Example:
    python3 convert.py ../media/img/totoro.png ../pico/frames/totoro.py totoro
"""

import sys
from PIL import Image


def convert(input_path, output_path, name):
    # Display dimensions
    WIDTH = 296
    HEIGHT = 152

    img = Image.open(input_path)

    # Resize to display dimensions if needed
    if img.size != (WIDTH, HEIGHT):
        print(f"Resizing from {img.size} to ({WIDTH}, {HEIGHT})")
        img = img.resize((WIDTH, HEIGHT), Image.LANCZOS)

    # Convert to pure black and white (1-bit)
    img = img.convert("1")

    pixels = list(img.getdata())

    # Pack pixels into bytes, 8 pixels per byte
    # E-ink convention: 0 = black, 1 = white
    # PIL "1" mode: 0 = black, 255 = white — so we invert
    byte_array = []
    for i in range(0, len(pixels), 8):
        byte = 0
        for bit in range(8):
            if i + bit < len(pixels):
                # 255 = white = 1, 0 = black = 0
                pixel = 1 if pixels[i + bit] == 255 else 0
                byte = (byte << 1) | pixel
        byte_array.append(byte)

    # Write output .py file
    with open(output_path, "w") as f:
        f.write(f"# Auto-generated from {input_path}\n")
        f.write(f"# {WIDTH}x{HEIGHT} pixels, 1-bit black and white\n\n")
        f.write(f"{name} = bytearray([\n    ")
        for i, b in enumerate(byte_array):
            f.write(f"0x{b:02X},")
            if (i + 1) % 16 == 0:
                f.write("\n    ")
            else:
                f.write(" ")
        f.write("\n])\n")
        f.write(f"\nWIDTH = {WIDTH}\n")
        f.write(f"HEIGHT = {HEIGHT}\n")

    print(f"Done. Written to {output_path}")
    print(f"Array size: {len(byte_array)} bytes")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python3 convert.py <input.png> <output.py> <name>")
        sys.exit(1)

    convert(sys.argv[1], sys.argv[2], sys.argv[3])

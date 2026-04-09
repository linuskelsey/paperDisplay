#!/usr/bin/env python3
"""
Verify a converted byte array by reconstructing it as a PNG.
Run this to visually check the conversion looks correct before flashing to the Pico.

Usage:
    python3 verify.py <input.py> <name> <output.png>

Example:
    python3 verify.py ../pico/frames/totoro.py totoro ../media/img/totoro_verify.png
"""

import sys
import importlib.util
from PIL import Image


def verify(input_path, name, output_path):
    WIDTH = 152
    HEIGHT = 296

    # Dynamically load the .py byte array file
    spec = importlib.util.spec_from_file_location(name, input_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    byte_array = getattr(module, name)

    # Unpack bytes back into pixels
    pixels = []
    for byte in byte_array:
        for bit in range(7, -1, -1):
            pixel = (byte >> bit) & 1
            # 1 = white (255), 0 = black (0)
            pixels.append(255 if pixel == 1 else 0)

    # Trim to exact pixel count (in case of padding)
    pixels = pixels[:WIDTH * HEIGHT]

    # Reconstruct image
    img = Image.new("L", (WIDTH, HEIGHT))
    img.putdata(pixels)
    img.save(output_path)

    print(f"Done. Saved verification image to {output_path}")
    print(f"Open it and check it looks correct.")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python3 verify.py <input.py> <name> <output.png>")
        sys.exit(1)

    verify(sys.argv[1], sys.argv[2], sys.argv[3])

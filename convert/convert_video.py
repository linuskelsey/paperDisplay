# convert/convert_video.py
# Converts a folder of PNG frames into byte array .py files for the Pico.
# Pads frames with black borders to fit the display canvas.
#
# Usage:
#   python3 convert/convert_video.py <frames_dir> <output_dir> <prefix>
#
# Example:
#   python3 convert/convert_video.py media/ani/twin_orb/frames_raw pico/frames twin_orb

import sys
import os
from PIL import Image

# Display resolution
DISPLAY_WIDTH  = 296
DISPLAY_HEIGHT = 152


def frame_to_bytearray(img):
    """
    Convert a PIL image to a packed bytearray.
    Pads with black to fit DISPLAY_WIDTH x DISPLAY_HEIGHT.
    Convention: 0 = black, 1 = white (matches convert.py)
    """
    # Convert to pure B&W (1-bit)
    img = img.convert('1')
    src_w, src_h = img.size

    # Create a black canvas at display resolution
    canvas = Image.new('1', (DISPLAY_WIDTH, DISPLAY_HEIGHT), 0)

    # Centre the source image on the canvas
    offset_x = (DISPLAY_WIDTH  - src_w) // 2
    offset_y = (DISPLAY_HEIGHT - src_h) // 2
    canvas.paste(img, (offset_x, offset_y))

    pixels = canvas.load()
    num_bytes = (DISPLAY_WIDTH * DISPLAY_HEIGHT) // 8
    buf = bytearray(num_bytes)

    for y in range(DISPLAY_HEIGHT):
        for x in range(DISPLAY_WIDTH):
            if pixels[x, y] == 255:  # white pixel
                byte_index = (y * DISPLAY_WIDTH + x) // 8
                bit_index  = 7 - ((y * DISPLAY_WIDTH + x) % 8)
                buf[byte_index] |= (1 << bit_index)

    return buf


def convert_frames(frames_dir, output_dir, prefix):
    os.makedirs(output_dir, exist_ok=True)

    # Collect and sort PNG files
    files = sorted([
        f for f in os.listdir(frames_dir)
        if f.lower().endswith('.png')
    ])

    if not files:
        print(f"No PNG files found in {frames_dir}")
        sys.exit(1)

    print(f"Found {len(files)} frames — converting...")

    for i, filename in enumerate(files, start=1):
        input_path  = os.path.join(frames_dir, filename)
        var_name    = f"{prefix}_{i:03d}"
        output_path = os.path.join(output_dir, f"{var_name}.py")

        img = Image.open(input_path)
        buf = frame_to_bytearray(img)

        with open(output_path, 'w') as f:
            f.write(f"# Auto-generated from {filename}\n")
            f.write(f"# {DISPLAY_WIDTH}x{DISPLAY_HEIGHT} pixels, 1-bit black and white\n\n")
            f.write(f"WIDTH  = {DISPLAY_WIDTH}\n")
            f.write(f"HEIGHT = {DISPLAY_HEIGHT}\n\n")
            f.write(f"{var_name} = bytearray([\n    ")

            hex_values = [f"0x{b:02X}" for b in buf]
            lines = [
                ', '.join(hex_values[j:j+16])
                for j in range(0, len(hex_values), 16)
            ]
            f.write(',\n    '.join(lines))
            f.write('\n])\n')

        print(f"  [{i:03d}/{len(files)}] {var_name}.py")

    print(f"\nDone. {len(files)} files written to {output_dir}/")


if __name__ == '__main__':
    if len(sys.argv) != 4:
        print("Usage: python3 convert/convert_video.py <frames_dir> <output_dir> <prefix>")
        sys.exit(1)

    convert_frames(sys.argv[1], sys.argv[2], sys.argv[3])

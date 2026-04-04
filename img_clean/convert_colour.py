# convert_colour.py
# Converts colour pixel art PNGs to B&W, padded to display resolution.
# Outputs B&W PNGs for touch-up in Procreate before final conversion.
#
# Pipeline:
#   1. Convert to greyscale
#   2. Apply edge enhancement (sharpening) to boost subject boundaries
#   3. Path A: apply luminance threshold — confident blacks and whites
#   4. Path B: apply Floyd-Steinberg dithering to sharpened greyscale
#   5. Combine: use threshold result where confident, dithering elsewhere
#   6. For uniform bright regions (e.g. skies): optionally force white
#   7. Pad to 296x152 with white borders
#   8. Apply dithered fade on left/right padding only (image → white)
#
# Colour originals are left untouched. B&W outputs are overwritten if they exist.
#
# Usage:
#   python3 convert_colour.py  (from anywhere)

import os
import numpy as np
from PIL import Image, ImageFilter
from scipy.ndimage import uniform_filter

# Display resolution
DISPLAY_WIDTH  = 296
DISPLAY_HEIGHT = 152

# --- Global defaults ---

# Luminance threshold — pixels clearly above this go white, clearly below go black
THRESHOLD = 140

# Confidence margin — pixels within this range of the threshold are ambiguous
# and handed to the dithering path instead.
MARGIN = 40

# Edge enhancement strength
# 1.0 = no sharpening, 2.0 = moderate, 3.0+ = aggressive
SHARPEN_STRENGTH = 2.0

# Uniform region detection — flat bright areas (e.g. skies) are forced to white.
# Set to 0 to disable for an image.
UNIFORMITY_VARIANCE = 15
UNIFORMITY_RADIUS   = 3

# --- Per-image overrides ---
# Use filename (not path) as key. Any global default can be overridden per image.
# Set UNIFORMITY_VARIANCE to 0 to disable uniform region detection for that image.
PER_IMAGE_OVERRIDES = {
    'spirited_away.png': {'uniformity_variance': 0},
}

# --- Paths ---
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
COLOUR_DIR = os.path.join(BASE_DIR, 'media', 'colour')
BW_DIR     = os.path.join(BASE_DIR, 'media', 'bw')


def get_params(filename):
    """Merge global defaults with any per-image overrides."""
    params = {
        'threshold':           THRESHOLD,
        'margin':              MARGIN,
        'sharpen_strength':    SHARPEN_STRENGTH,
        'uniformity_variance': UNIFORMITY_VARIANCE,
        'uniformity_radius':   UNIFORMITY_RADIUS,
    }
    params.update(PER_IMAGE_OVERRIDES.get(filename, {}))
    return params


def sharpen(grey, strength):
    """Apply edge enhancement to a greyscale image at a given strength."""
    if strength <= 1.0:
        return grey
    sharpened = grey.filter(ImageFilter.SHARPEN)
    passes = int(strength)
    for _ in range(passes - 1):
        sharpened = sharpened.filter(ImageFilter.SHARPEN)
    fraction = strength - passes
    if fraction > 0:
        arr_orig  = np.array(grey,      dtype=np.float32)
        arr_sharp = np.array(sharpened, dtype=np.float32)
        blended   = arr_orig + fraction * (arr_sharp - arr_orig)
        blended   = np.clip(blended, 0, 255).astype(np.uint8)
        sharpened = Image.fromarray(blended, mode='L')
    return sharpened


def apply_dithered_fade(canvas_arr, offset_x, offset_y, img_w, img_h):
    """
    Apply a dithered fade on left and right padding only.
    Fades from the image edge outward to white.
    Vertical padding rows (above and below the image) are left as white.
    """
    h, w = canvas_arr.shape

    # Only operate on rows that contain image content
    row_start = offset_y
    row_end   = offset_y + img_h

    # Left fade: columns 0 to offset_x
    left_width = offset_x
    if left_width > 0:
        for col in range(left_width):
            # Distance from image edge — 0 at image boundary, left_width-1 at canvas edge
            dist = left_width - col
            # Probability of being white increases with distance from image
            white_prob = dist / left_width
            for row in range(row_start, row_end):
                # Ordered dither using pixel position for a structured pattern
                threshold_val = ((row * 7 + col * 3) % 16) / 16.0
                canvas_arr[row, col] = 255 if white_prob > threshold_val else 0

    # Right fade: columns offset_x + img_w to end
    right_start = offset_x + img_w
    right_width = w - right_start
    if right_width > 0:
        for col in range(right_start, w):
            dist = col - right_start + 1
            white_prob = dist / right_width
            for row in range(row_start, row_end):
                threshold_val = ((row * 7 + col * 3) % 16) / 16.0
                canvas_arr[row, col] = 255 if white_prob > threshold_val else 0

    return canvas_arr


def convert_image(input_path, output_path, params):
    img  = Image.open(input_path).convert('RGB')
    grey = img.convert('L')

    # Resize to fit display, maintaining aspect ratio
    src_w, src_h = grey.size
    scale = min(DISPLAY_WIDTH / src_w, DISPLAY_HEIGHT / src_h)
    new_w = int(src_w * scale)
    new_h = int(src_h * scale)
    grey_resized = grey.resize((new_w, new_h), Image.LANCZOS)

    # Edge enhancement
    enhanced = sharpen(grey_resized, params['sharpen_strength'])

    # Path A: luminance threshold
    threshold_bw = enhanced.point(
        lambda p: 255 if p >= params['threshold'] else 0, '1'
    )

    # Path B: Floyd-Steinberg dithering
    dithered_bw = enhanced.convert('1', dither=Image.Dither.FLOYDSTEINBERG)

    grey_arr      = np.array(enhanced,                  dtype=np.float32)
    threshold_arr = np.array(threshold_bw.convert('L'), dtype=np.uint8)
    dithered_arr  = np.array(dithered_bw.convert('L'),  dtype=np.uint8)

    # Confidence mask
    t = params['threshold']
    m = params['margin']
    confident = (grey_arr >= (t + m)) | (grey_arr <= (t - m))

    # Combine
    result_arr = dithered_arr.copy()
    result_arr[confident] = threshold_arr[confident]

    # Uniform bright region detection (optional)
    uv = params['uniformity_variance']
    if uv > 0:
        r       = params['uniformity_radius']
        mean    = uniform_filter(grey_arr, size=r * 2 + 1)
        mean_sq = uniform_filter(grey_arr ** 2, size=r * 2 + 1)
        variance = mean_sq - mean ** 2
        uniform_bright = (variance < uv) & (grey_arr >= t)
        result_arr[uniform_bright] = 255

    result = Image.fromarray(result_arr.astype(np.uint8), mode='L').convert('1')

    # Pad onto white canvas
    canvas   = Image.new('1', (DISPLAY_WIDTH, DISPLAY_HEIGHT), 1)
    offset_x = (DISPLAY_WIDTH  - new_w) // 2
    offset_y = (DISPLAY_HEIGHT - new_h) // 2
    canvas.paste(result, (offset_x, offset_y))

    # Apply dithered fade on left/right padding
    canvas_arr = np.array(canvas.convert('L'), dtype=np.uint8)
    canvas_arr = apply_dithered_fade(canvas_arr, offset_x, offset_y, new_w, new_h)

    final = Image.fromarray(canvas_arr, mode='L').convert('1')
    final.save(output_path)


def main():
    os.makedirs(BW_DIR, exist_ok=True)

    files = sorted([
        f for f in os.listdir(COLOUR_DIR)
        if f.lower().endswith('.png')
    ])

    if not files:
        print("No PNG files found in " + COLOUR_DIR)
        return

    print(f"Found {len(files)} file(s) — converting...")

    for filename in files:
        input_path  = os.path.join(COLOUR_DIR, filename)
        stem        = os.path.splitext(filename)[0]
        output_name = stem + '_bw.png'
        output_path = os.path.join(BW_DIR, output_name)
        params      = get_params(filename)

        try:
            convert_image(input_path, output_path, params)
            print(f"  {filename} → {output_name}")
        except Exception as e:
            print(f"  Failed: {filename} — {e}")

    print(f"\nDone. B&W PNGs written to {BW_DIR}/")


main()

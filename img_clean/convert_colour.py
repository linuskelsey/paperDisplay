#!/usr/bin/env python3
"""
convert_colour.py
Converts colour pixel art PNGs to B&W, padded and centred to display
resolution (296 × 152 px), and optionally copies them into media/img/.
 
This is the first stage of the colour image pipeline. Output B&W PNGs are
then processed by convert.py (which applies the 90° rotation and packs them
into byte arrays for the Pico).
 
Pipeline per image:
    1. Greyscale conversion
    2. Edge enhancement (sharpening)
    3. Confident pixels (far from threshold) → hard threshold
    4. Ambiguous pixels (near threshold) → Floyd-Steinberg dithering
    5. Optional: uniform bright regions forced to white
    6. Pad to 296 × 152 px with white borders
    7. Dithered fade on left/right padding only
 
Per-image parameter overrides can be set in PER_IMAGE_OVERRIDES at the top
of this file. Run with --preview for an interactive tuning loop.
 
Usage:
    python img_clean/convert_colour.py              # batch convert + auto-copy to media/img/
    python img_clean/convert_colour.py --preview    # convert + inline preview + retune loop
"""

import os
import sys
import shutil
import argparse
import numpy as np
from PIL import Image, ImageFilter, ImageDraw, ImageFont
from scipy.ndimage import uniform_filter

DISPLAY_WIDTH        = 296
DISPLAY_HEIGHT       = 152
PREVIEW_PIXEL_WIDTH  = DISPLAY_WIDTH * 4   # 1184px — chafa scales to terminal
PREVIEW_LABEL_HEIGHT = 22

THRESHOLD           = 140
MARGIN              = 40
SHARPEN_STRENGTH    = 2.0
UNIFORMITY_VARIANCE = 15
UNIFORMITY_RADIUS   = 3

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR    = os.path.dirname(BASE_DIR)
COLOUR_DIR  = os.path.join(BASE_DIR, 'media', 'colour')
BW_DIR      = os.path.join(BASE_DIR, 'media', 'bw')
PREVIEW_DIR = os.path.join(BASE_DIR, 'media', 'preview')
IMG_DIR     = os.path.join(ROOT_DIR, 'media', 'img')


def get_params():
    return {
        'threshold':           THRESHOLD,
        'margin':              MARGIN,
        'sharpen_strength':    SHARPEN_STRENGTH,
        'uniformity_variance': UNIFORMITY_VARIANCE,
        'uniformity_radius':   UNIFORMITY_RADIUS,
    }


def copy_to_media(bw_path, filename):
    """Copy the finished B&W PNG into media/img/, dropping the _bw suffix."""
    os.makedirs(IMG_DIR, exist_ok=True)
    stem = os.path.splitext(filename)[0]
    # Strip trailing _bw if present
    if stem.endswith('_bw'):
        stem = stem[:-3]
    dest = os.path.join(IMG_DIR, stem + '.png')
    shutil.copy2(bw_path, dest)
    print(f"  Copied -> media/img/{stem}.png")


def sharpen(grey, strength):
    if strength <= 1.0:
        return grey
    sharpened = grey.filter(ImageFilter.SHARPEN)
    for _ in range(int(strength) - 1):
        sharpened = sharpened.filter(ImageFilter.SHARPEN)
    fraction = strength - int(strength)
    if fraction > 0:
        arr_orig  = np.array(grey,      dtype=np.float32)
        arr_sharp = np.array(sharpened, dtype=np.float32)
        blended   = np.clip(arr_orig + fraction * (arr_sharp - arr_orig), 0, 255).astype(np.uint8)
        sharpened = Image.fromarray(blended, mode='L')
    return sharpened


def apply_dithered_fade(canvas_arr, offset_x, offset_y, img_w, img_h):
    h, w = canvas_arr.shape
    row_start, row_end = offset_y, offset_y + img_h
    left_width = offset_x
    if left_width > 0:
        for col in range(left_width):
            dist = left_width - col
            wp   = dist / left_width
            for row in range(row_start, row_end):
                tv = ((row * 7 + col * 3) % 16) / 16.0
                canvas_arr[row, col] = 255 if wp > tv else 0
    right_start = offset_x + img_w
    right_width = w - right_start
    if right_width > 0:
        for col in range(right_start, w):
            dist = col - right_start + 1
            wp   = dist / right_width
            for row in range(row_start, row_end):
                tv = ((row * 7 + col * 3) % 16) / 16.0
                canvas_arr[row, col] = 255 if wp > tv else 0
    return canvas_arr


def convert_image(input_path, output_path, params):
    img  = Image.open(input_path).convert('RGB')
    grey = img.convert('L')

    src_w, src_h = grey.size
    scale        = min(DISPLAY_WIDTH / src_w, DISPLAY_HEIGHT / src_h)
    new_w        = int(src_w * scale)
    new_h        = int(src_h * scale)
    grey_resized = grey.resize((new_w, new_h), Image.LANCZOS)

    enhanced     = sharpen(grey_resized, params['sharpen_strength'])
    threshold_bw = enhanced.point(lambda p: 255 if p >= params['threshold'] else 0, '1')
    dithered_bw  = enhanced.convert('1', dither=Image.Dither.FLOYDSTEINBERG)

    grey_arr      = np.array(enhanced,                  dtype=np.float32)
    threshold_arr = np.array(threshold_bw.convert('L'), dtype=np.uint8)
    dithered_arr  = np.array(dithered_bw.convert('L'),  dtype=np.uint8)

    t          = params['threshold']
    m          = params['margin']
    confident  = (grey_arr >= (t + m)) | (grey_arr <= (t - m))
    result_arr = dithered_arr.copy()
    result_arr[confident] = threshold_arr[confident]

    uv = params['uniformity_variance']
    if uv > 0:
        r       = params['uniformity_radius']
        mean    = uniform_filter(grey_arr,      size=r * 2 + 1)
        mean_sq = uniform_filter(grey_arr ** 2, size=r * 2 + 1)
        variance       = mean_sq - mean ** 2
        uniform_bright = (variance < uv) & (grey_arr >= t)
        result_arr[uniform_bright] = 255

    result   = Image.fromarray(result_arr.astype(np.uint8), mode='L').convert('1')
    canvas   = Image.new('1', (DISPLAY_WIDTH, DISPLAY_HEIGHT), 1)
    offset_x = (DISPLAY_WIDTH  - new_w) // 2
    offset_y = (DISPLAY_HEIGHT - new_h) // 2
    canvas.paste(result, (offset_x, offset_y))

    canvas_arr = np.array(canvas.convert('L'), dtype=np.uint8)
    canvas_arr = apply_dithered_fade(canvas_arr, offset_x, offset_y, new_w, new_h)
    final = Image.fromarray(canvas_arr, mode='L').convert('1')
    final.save(output_path)
    return final


def build_preview(original_path, bw_image, params, output_path):
    pw = PREVIEW_PIXEL_WIDTH
    ph = int(pw * DISPLAY_HEIGHT / DISPLAY_WIDTH)
    lh = PREVIEW_LABEL_HEIGHT

    total_w = pw * 2 + 3
    total_h = ph + lh + 2
    canvas  = Image.new('RGB', (total_w, total_h), (30, 30, 30))

    orig = Image.open(original_path).convert('RGB')
    orig.thumbnail((pw, ph), Image.LANCZOS)
    left_panel = Image.new('RGB', (pw, ph), (255, 255, 255))
    left_panel.paste(orig, ((pw - orig.width) // 2, (ph - orig.height) // 2))
    canvas.paste(left_panel, (1, 1))

    bw_scaled = bw_image.convert('RGB').resize((pw, ph), Image.NEAREST)
    canvas.paste(bw_scaled, (pw + 2, 1))

    draw = ImageDraw.Draw(canvas)
    draw.line([(pw + 1, 1), (pw + 1, ph)], fill=(80, 80, 80), width=1)

    label_y = ph + 2
    draw.rectangle([(0, label_y), (total_w, total_h)], fill=(20, 20, 20))

    right_label = (f"t={params['threshold']}  m={params['margin']}  "
                   f"s={params['sharpen_strength']}  "
                   f"uv={params['uniformity_variance']}  ur={params['uniformity_radius']}")
    bw_arr    = np.array(bw_image.convert('L'))
    black_pct = 100 * np.sum(bw_arr == 0) / bw_arr.size
    stats     = f"black={black_pct:.1f}%  white={100-black_pct:.1f}%"

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 18)
    except Exception:
        font = ImageFont.load_default()

    draw.text((6,      label_y + 3), os.path.basename(original_path), fill=(200, 200, 200), font=font)
    draw.text((pw + 8, label_y + 3), right_label,                     fill=(180, 220, 180), font=font)
    bbox    = font.getbbox(stats)
    stats_w = bbox[2] - bbox[0]
    draw.text((total_w - stats_w - 8, label_y + 3), stats, fill=(160, 200, 220), font=font)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    canvas.save(output_path)
    return output_path


def build_variant_thumb(bw_image, label, output_path):
    pw = PREVIEW_PIXEL_WIDTH
    ph = int(pw * DISPLAY_HEIGHT / DISPLAY_WIDTH)
    lh = PREVIEW_LABEL_HEIGHT

    canvas = Image.new('RGB', (pw, ph + lh + 2), (30, 30, 30))
    canvas.paste(bw_image.convert('RGB').resize((pw, ph), Image.NEAREST), (0, 1))

    draw = ImageDraw.Draw(canvas)
    label_y = ph + 2
    draw.rectangle([(0, label_y), (pw, ph + lh + 2)], fill=(20, 20, 20))

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 18)
    except Exception:
        font = ImageFont.load_default()

    draw.text((6, label_y + 3), label, fill=(255, 200, 80), font=font)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    canvas.save(output_path)
    return output_path


def prompt_retune(filename, input_path, output_path, preview_path):
    import display
    import tune as tune_mod

    params = get_params()

    while True:
        display.show(preview_path)
        try:
            answer = input("  Happy with this? [y / retune / q]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False

        if answer == 'q':
            return False

        if answer in ('y', ''):
            copy_to_media(output_path, os.path.basename(output_path))
            return True

        if answer in ('r', 'retune', 't', 'tune'):
            result = tune_mod.run_tuner(input_path)
            if result is None:
                continue
            params = result
            print("  Re-converting...")
            bw = convert_image(input_path, output_path, params)
            build_preview(input_path, bw, params, preview_path)
            continue

        print("  Please enter y, retune, or q.")


def process_image(filename, interactive):
    input_path   = os.path.join(COLOUR_DIR, filename)
    stem         = os.path.splitext(filename)[0]
    output_path  = os.path.join(BW_DIR,      stem + '_bw.png')
    preview_path = os.path.join(PREVIEW_DIR, stem + '_preview.png')
    params       = get_params()

    bw = convert_image(input_path, output_path, params)

    if not interactive:
        print(f"  {filename} -> bw/{stem}_bw.png")
        copy_to_media(output_path, stem + '_bw.png')
        return True

    build_preview(input_path, bw, params, preview_path)
    return prompt_retune(filename, input_path, output_path, preview_path)


def main():
    parser = argparse.ArgumentParser(description='Convert colour PNGs to B&W for the e-ink display.')
    parser.add_argument('--preview', action='store_true',
                        help='Interactive mode: show inline preview and retune loop')
    args = parser.parse_args()

    os.makedirs(BW_DIR, exist_ok=True)
    os.makedirs(IMG_DIR, exist_ok=True)
    if args.preview:
        os.makedirs(PREVIEW_DIR, exist_ok=True)

    files = sorted([f for f in os.listdir(COLOUR_DIR) if f.lower().endswith('.png')])
    if not files:
        print(f"No PNG files found in {COLOUR_DIR}")
        return

    mode = 'interactive' if args.preview else 'batch'
    print(f"Found {len(files)} file(s) — converting ({mode})...\n")

    for i, filename in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {filename}")
        try:
            keep_going = process_image(filename, interactive=args.preview)
        except Exception as e:
            print(f"  Failed: {e}")
            keep_going = True

        if not keep_going:
            print("\nStopped early.")
            break
        print()

    print("Done.")


if __name__ == '__main__':
    main()

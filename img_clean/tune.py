#!/usr/bin/env python3
"""
tune.py
Auto-parameter tuner for convert_colour.py.

Normally called inline by convert_colour.py --preview when you answer 'retune'.
Can also be run standalone.

Standalone usage:
  python3 convert/tune.py <image.png>
  python3 convert/tune.py <image.png> --full          # also sweep threshold + sharpening
  python3 convert/tune.py <image.png> --uv 0 5 10 20  # manual UV values
"""

import os
import sys
import re
import argparse
import itertools
import tempfile
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from scipy.ndimage import uniform_filter

DISPLAY_WIDTH  = 296
DISPLAY_HEIGHT = 152

BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR       = os.path.dirname(BASE_DIR)
CONVERT_COLOUR = os.path.join(BASE_DIR, 'convert_colour.py')

DEFAULT_THRESHOLD        = 140
DEFAULT_MARGIN           = 40
DEFAULT_SHARPEN_STRENGTH = 2.0
DEFAULT_UV               = 15
DEFAULT_UR               = 3

GLOBAL_DEFAULTS = {
    'threshold':           DEFAULT_THRESHOLD,
    'margin':              DEFAULT_MARGIN,
    'sharpen_strength':    DEFAULT_SHARPEN_STRENGTH,
    'uniformity_variance': DEFAULT_UV,
    'uniformity_radius':   DEFAULT_UR,
}

UV_COARSE = [0, 5, 10, 15, 25, 40, 60]
T_COARSE  = [100, 120, 140, 160, 180]
S_COARSE  = [1.0, 2.0, 3.0]


# ---------------------------------------------------------------------------
# Pipeline (kept in sync with convert_colour.py)
# ---------------------------------------------------------------------------

def _sharpen(grey, strength):
    if strength <= 1.0:
        return grey
    sharpened = grey.filter(ImageFilter.SHARPEN)
    for _ in range(int(strength) - 1):
        sharpened = sharpened.filter(ImageFilter.SHARPEN)
    fraction = strength - int(strength)
    if fraction > 0:
        a = np.array(grey,      dtype=np.float32)
        b = np.array(sharpened, dtype=np.float32)
        sharpened = Image.fromarray(
            np.clip(a + fraction * (b - a), 0, 255).astype(np.uint8), mode='L'
        )
    return sharpened


def _apply_dithered_fade(canvas_arr, offset_x, offset_y, img_w, img_h):
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


def _run_pipeline(grey_resized, new_w, new_h, threshold, margin,
                  sharpen_strength, uv, ur):
    enhanced     = _sharpen(grey_resized, sharpen_strength)
    threshold_bw = enhanced.point(lambda p: 255 if p >= threshold else 0, '1')
    dithered_bw  = enhanced.convert('1', dither=Image.Dither.FLOYDSTEINBERG)

    grey_arr      = np.array(enhanced,                  dtype=np.float32)
    threshold_arr = np.array(threshold_bw.convert('L'), dtype=np.uint8)
    dithered_arr  = np.array(dithered_bw.convert('L'),  dtype=np.uint8)

    confident  = (grey_arr >= (threshold + margin)) | (grey_arr <= (threshold - margin))
    result_arr = dithered_arr.copy()
    result_arr[confident] = threshold_arr[confident]

    if uv > 0:
        mean    = uniform_filter(grey_arr,      size=ur * 2 + 1)
        mean_sq = uniform_filter(grey_arr ** 2, size=ur * 2 + 1)
        variance       = mean_sq - mean ** 2
        uniform_bright = (variance < uv) & (grey_arr >= threshold)
        result_arr[uniform_bright] = 255

    result   = Image.fromarray(result_arr.astype(np.uint8), mode='L').convert('1')
    canvas   = Image.new('1', (DISPLAY_WIDTH, DISPLAY_HEIGHT), 1)
    offset_x = (DISPLAY_WIDTH  - new_w) // 2
    offset_y = (DISPLAY_HEIGHT - new_h) // 2
    canvas.paste(result, (offset_x, offset_y))
    canvas_arr = np.array(canvas.convert('L'), dtype=np.uint8)
    canvas_arr = _apply_dithered_fade(canvas_arr, offset_x, offset_y, new_w, new_h)
    return Image.fromarray(canvas_arr, mode='L').convert('1')


def _load_and_resize(input_path):
    grey  = Image.open(input_path).convert('L')
    src_w, src_h = grey.size
    scale = min(DISPLAY_WIDTH / src_w, DISPLAY_HEIGHT / src_h)
    new_w = int(src_w * scale)
    new_h = int(src_h * scale)
    return grey.resize((new_w, new_h), Image.LANCZOS), new_w, new_h


# ---------------------------------------------------------------------------
# Patching PER_IMAGE_OVERRIDES
# ---------------------------------------------------------------------------

def _format_value(v):
    if isinstance(v, float):
        return str(v)
    return repr(v)


def patch_overrides(filename, params):
    if not os.path.isfile(CONVERT_COLOUR):
        print(f"  Warning: could not find {CONVERT_COLOUR} — skipping patch.")
        return

    with open(CONVERT_COLOUR, 'r') as f:
        source = f.read()

    overrides = {k: v for k, v in params.items()
                 if v != GLOBAL_DEFAULTS.get(k)}

    if overrides:
        inner     = ', '.join(f"'{k}': {_format_value(v)}" for k, v in overrides.items())
        new_entry = f"    '{filename}': {{{inner}}},"
    else:
        new_entry = None

    entry_pattern = re.compile(
        r"([ \t]*'" + re.escape(filename) + r"'[ \t]*:[ \t]*\{[^}]*\},?[ \t]*\n)",
        re.MULTILINE
    )

    if entry_pattern.search(source):
        if new_entry:
            source = entry_pattern.sub(new_entry + '\n', source)
        else:
            source = entry_pattern.sub('', source)
    elif new_entry:
        dict_close = re.compile(r'(PER_IMAGE_OVERRIDES\s*=\s*\{[^}]*)(\})', re.DOTALL)
        m = dict_close.search(source)
        if m:
            source = source[:m.start(2)] + new_entry + '\n' + source[m.start(2):]

    with open(CONVERT_COLOUR, 'w') as f:
        f.write(source)

    if overrides:
        print(f"  Patched PER_IMAGE_OVERRIDES['{filename}'] = {overrides}")
    else:
        print(f"  Removed override for '{filename}' (matches global defaults)")


# ---------------------------------------------------------------------------
# Core tuner
# ---------------------------------------------------------------------------

def run_tuner(input_path, uv_values=None, full=False):
    """
    Run the grid search, print each variant inline in the terminal,
    prompt for a pick, then patch convert_colour.py.

    Returns True if the user aborted (q), False if a variant was applied.
    """
    import display

    filename = os.path.basename(input_path)
    uv_values = uv_values or UV_COARSE

    if full:
        param_sets = [
            {'threshold': t, 'margin': DEFAULT_MARGIN,
             'sharpen_strength': s, 'uniformity_variance': uv,
             'uniformity_radius': DEFAULT_UR}
            for t, s, uv in itertools.product(T_COARSE, S_COARSE, uv_values)
        ]
    else:
        param_sets = [
            {'threshold': DEFAULT_THRESHOLD, 'margin': DEFAULT_MARGIN,
             'sharpen_strength': DEFAULT_SHARPEN_STRENGTH,
             'uniformity_variance': uv, 'uniformity_radius': DEFAULT_UR}
            for uv in uv_values
        ]

    print(f"  Tuning {filename}: {len(param_sets)} variant(s)...\n")
    grey_resized, new_w, new_h = _load_and_resize(input_path)

    # Use a temp dir for variant thumbnails so they don't pollute media/
    tmp_dir = tempfile.mkdtemp(prefix='paperDisplay_tune_')
    results = []

    try:
        for i, p in enumerate(param_sets, 1):
            bw = _run_pipeline(
                grey_resized, new_w, new_h,
                p['threshold'], p['margin'],
                p['sharpen_strength'], p['uniformity_variance'],
                p['uniformity_radius']
            )

            if full:
                label = f"[{i}] t={p['threshold']}  s={p['sharpen_strength']}  uv={p['uniformity_variance']}"
            else:
                label = f"[{i}] uv={p['uniformity_variance']}"

            # Build a terminal-width single-panel thumb and render it inline
            import convert_colour as cc
            thumb_path = os.path.join(tmp_dir, f"variant_{i:03d}.png")
            cc.build_variant_thumb(bw, label, thumb_path)
            display.show(thumb_path)
            print()

            results.append((label, bw, p))

    finally:
        pass  # keep tmp_dir alive until after the prompt

    # Prompt
    while True:
        try:
            raw = input(f"  Pick a variant [1-{len(results)}]  (or 'q' to go back): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            import shutil; shutil.rmtree(tmp_dir, ignore_errors=True)
            return True

        if raw.lower() == 'q':
            import shutil; shutil.rmtree(tmp_dir, ignore_errors=True)
            return True

        try:
            choice = int(raw)
            if 1 <= choice <= len(results):
                break
            print(f"  Enter a number between 1 and {len(results)}.")
        except ValueError:
            print("  Invalid input.")

    import shutil; shutil.rmtree(tmp_dir, ignore_errors=True)

    chosen_label, _, chosen_params = results[choice - 1]
    print(f"  Applying variant {choice}: {chosen_label.lstrip()}")
    patch_overrides(filename, chosen_params)
    return False


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Tune convert_colour.py parameters for one image.')
    parser.add_argument('image', help='Path to the colour PNG to tune')
    parser.add_argument('--full', action='store_true',
                        help='Also sweep threshold and sharpen_strength')
    parser.add_argument('--uv', nargs='+', type=float, metavar='N',
                        help='Manual uniformity_variance values')
    args = parser.parse_args()

    if not os.path.isfile(args.image):
        print(f"File not found: {args.image}")
        sys.exit(1)

    aborted = run_tuner(args.image, uv_values=args.uv, full=args.full)
    if not aborted:
        print(f"\nOverride written. Run convert_colour.py --preview to see the result.")


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
tune.py
Guided parameter tuner for convert_colour.py.
 
Steps through threshold → sharpening → uniformity_variance one at a time,
rendering variants inline in the terminal at each step so you can scroll up
to compare before picking. Supports back-navigation between steps.
 
On completion, patches PER_IMAGE_OVERRIDES in convert_colour.py with the
chosen values so results persist across runs.
 
Normally called from inside convert_colour.py --preview (via the 'retune'
prompt). Can also be run standalone against any colour PNG.
 
Standalone usage:
    python img_clean/tune.py <image.png>
    python img_clean/tune.py <image.png> --full     # wider value ranges
"""

import os
import sys
import argparse
import tempfile
import shutil
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from scipy.ndimage import uniform_filter

DISPLAY_WIDTH  = 296
DISPLAY_HEIGHT = 152

BASE_DIR       = os.path.dirname(os.path.abspath(__file__))

DEFAULT_THRESHOLD        = 140
DEFAULT_MARGIN           = 40
DEFAULT_SHARPEN_STRENGTH = 2.0
DEFAULT_UV               = 15
DEFAULT_UR               = 3

# Values offered at each tuning step (normal mode)
THRESHOLD_VALUES = [100, 120, 140, 160, 180]
SHARPEN_VALUES   = [1.0, 2.0, 3.0]
UV_VALUES        = [0, 10, 25, 50]

# Wider ranges for --full mode
THRESHOLD_VALUES_FULL = [80, 100, 120, 140, 160, 180, 200]
SHARPEN_VALUES_FULL   = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0]
UV_VALUES_FULL        = [0, 5, 10, 20, 40, 80]

STEPS = ['threshold', 'sharpen_strength', 'uniformity_variance']


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
# One tuning step — render variants for a single parameter, prompt for pick
# ---------------------------------------------------------------------------

def _run_step(step_name, values, fixed_params, grey_resized, new_w, new_h,
              tmp_dir, step_num, total_steps):
    """
    Render one variant per value for `step_name`, print them inline,
    then prompt for a choice.

    Returns:
      (chosen_value, 'back')  — user typed b
      (chosen_value, 'ok')    — user picked a variant
      (None,         'quit')  — user typed q
    """
    import display
    import convert_colour as cc

    param_labels = {
        'threshold':           'threshold',
        'sharpen_strength':    'sharpening',
        'uniformity_variance': 'uniformity (UV)',
    }

    print(f"\n  Step {step_num}/{total_steps} — {param_labels[step_name]}  "
          f"(fixed: {'  '.join(f'{k}={v}' for k, v in fixed_params.items() if k != 'margin' and k != 'uniformity_radius')})")

    variants = []
    for i, val in enumerate(values, 1):
        params = {**fixed_params, step_name: val}
        bw = _run_pipeline(
            grey_resized, new_w, new_h,
            params['threshold'], params['margin'],
            params['sharpen_strength'], params['uniformity_variance'],
            params['uniformity_radius']
        )
        label = f"[{i}] {step_name.split('_')[0]}={val}"
        thumb_path = os.path.join(tmp_dir, f"step{step_num}_{i:02d}.png")
        cc.build_variant_thumb(bw, label, thumb_path)
        display.show(thumb_path)
        print()
        variants.append(val)

    back_hint = "  (b = go back)" if step_num > 1 else ""
    while True:
        try:
            raw = input(f"  Pick [1-{len(variants)}]{back_hint}  or q to abort: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return None, 'quit'

        if raw == 'q':
            return None, 'quit'
        if raw == 'b' and step_num > 1:
            return None, 'back'
        try:
            choice = int(raw)
            if 1 <= choice <= len(variants):
                return variants[choice - 1], 'ok'
            print(f"  Enter a number between 1 and {len(variants)}.")
        except ValueError:
            print("  Invalid input.")


# ---------------------------------------------------------------------------
# Core tuner
# ---------------------------------------------------------------------------

def run_tuner(input_path, full=False):
    """
    Step through threshold → sharpening → UV one at a time.
    Returns True if aborted, False if params were applied.
    """
    filename = os.path.basename(input_path)

    t_values  = THRESHOLD_VALUES_FULL if full else THRESHOLD_VALUES
    s_values  = SHARPEN_VALUES_FULL   if full else SHARPEN_VALUES
    uv_values = UV_VALUES_FULL        if full else UV_VALUES

    step_values = {
        'threshold':           t_values,
        'sharpen_strength':    s_values,
        'uniformity_variance': uv_values,
    }

    grey_resized, new_w, new_h = _load_and_resize(input_path)
    tmp_dir = tempfile.mkdtemp(prefix='paperDisplay_tune_')

    # Chosen values accumulate as we step forward
    chosen = {}

    try:
        step_idx = 0
        while step_idx < len(STEPS):
            step_name = STEPS[step_idx]

            # Build fixed params from defaults + whatever we've already chosen
            fixed = {
                'threshold':           chosen.get('threshold',           DEFAULT_THRESHOLD),
                'margin':              DEFAULT_MARGIN,
                'sharpen_strength':    chosen.get('sharpen_strength',    DEFAULT_SHARPEN_STRENGTH),
                'uniformity_variance': chosen.get('uniformity_variance', DEFAULT_UV),
                'uniformity_radius':   DEFAULT_UR,
            }

            val, action = _run_step(
                step_name, step_values[step_name], fixed,
                grey_resized, new_w, new_h, tmp_dir,
                step_idx + 1, len(STEPS)
            )

            if action == 'quit':
                return None
            elif action == 'back':
                # Remove the previous step's choice and go back
                prev_step = STEPS[step_idx - 1]
                chosen.pop(prev_step, None)
                step_idx -= 1
            elif action == 'ok':
                chosen[step_name] = val
                step_idx += 1

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # Build final params and patch
    final_params = {
        'threshold':           chosen['threshold'],
        'margin':              DEFAULT_MARGIN,
        'sharpen_strength':    chosen['sharpen_strength'],
        'uniformity_variance': chosen['uniformity_variance'],
        'uniformity_radius':   DEFAULT_UR,
    }
    summary = (f"t={final_params['threshold']}  "
               f"s={final_params['sharpen_strength']}  "
               f"uv={final_params['uniformity_variance']}")
    print(f"\n  Applying: {summary}")
    return final_params


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Guided parameter tuner for convert_colour.py.'
    )
    parser.add_argument('image', help='Path to the colour PNG to tune')
    parser.add_argument('--full', action='store_true',
                        help='Use wider value ranges at each step')
    args = parser.parse_args()

    if not os.path.isfile(args.image):
        print(f"File not found: {args.image}")
        sys.exit(1)

    aborted = run_tuner(args.image, full=args.full)
    if not aborted:
        print(f"Done. Run convert_colour.py --preview to see the result.")


if __name__ == '__main__':
    main()

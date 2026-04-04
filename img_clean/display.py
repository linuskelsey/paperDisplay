#!/usr/bin/env python3
"""
display.py
Terminal image rendering for convert_colour.py and tune.py.
Tries renderers in order: kitten icat -> timg -> chafa -> external open.

All rendering is width-constrained to the current terminal width so nothing
wraps on narrow terminals.
"""

import os
import sys
import shutil
import subprocess
import platform

# Minimum sensible column width — below this we skip inline and open externally
MIN_COLS = 40


def _term_cols():
    """Return current terminal width in columns, with a safe fallback."""
    try:
        return os.get_terminal_size().columns
    except OSError:
        return 80


def _has(cmd):
    return shutil.which(cmd) is not None


def _open_external(path):
    """Open a file with the OS default viewer, non-blocking."""
    system = platform.system()
    try:
        if system == 'Darwin':
            subprocess.Popen(['open', path])
        elif system == 'Windows':
            os.startfile(path)
        else:
            subprocess.Popen(['xdg-open', path])
        print(f"  Opened externally: {path}")
    except Exception as e:
        print(f"  Could not open {path}: {e}")


def _render_kitten(path, cols):
    """Render via kitten icat (Kitty/Ghostty graphics protocol)."""
    try:
        subprocess.run(
            ['kitten', 'icat', '--align=left', f'--scale-up',
             '--place', f'{cols}x9999@0x0', path],
            check=True
        )
        return True
    except Exception:
        return False


def _render_timg(path, cols):
    """Render via timg."""
    try:
        subprocess.run(
            ['timg', f'--width={cols}', '--fit-width', path],
            check=True
        )
        return True
    except Exception:
        return False


def _render_chafa(path, cols):
    """Render via chafa (Unicode block characters, works in any terminal)."""
    try:
        subprocess.run(
            ['chafa', '--size', f'{cols}x', '--fit-width', path],
            check=True
        )
        return True
    except Exception:
        return False


def show(path, label=None):
    """
    Render an image inline in the terminal, constrained to terminal width.
    Falls back gracefully through available renderers.
    If the terminal is too narrow, opens externally instead.
    """
    cols = _term_cols()

    if label:
        print(f"  {label}")

    if cols < MIN_COLS:
        print(f"  Terminal too narrow ({cols} cols) — opening externally.")
        _open_external(path)
        return

    # Try renderers in preference order
    if _has('kitten') and _render_kitten(path, cols):
        return
    if _has('timg') and _render_timg(path, cols):
        return
    if _has('chafa') and _render_chafa(path, cols):
        return

    # Nothing worked inline — open externally
    print(f"  No inline renderer found (install timg or chafa for inline display).")
    _open_external(path)


def show_sequence(items):
    """
    Render a sequence of (label, image_path) tuples one by one.
    Used for the retune contact flow — prints each variant sequentially
    so the user can scroll up to compare.
    """
    for label, path in items:
        print()
        show(path, label=label)
        print()

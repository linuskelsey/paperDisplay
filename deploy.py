#!/usr/bin/env python3
"""
deploy.py
Deploys Pico source files to the device via mpremote.

Permissions note:
    To avoid needing sudo chmod on every connect, set up a udev rule once:
        echo 'SUBSYSTEMS=="usb", ATTRS{idVendor}=="2e8a", MODE="0666"' | sudo tee /etc/udev/rules.d/49-pico.rules
        sudo udevadm control --reload-rules && sudo udevadm trigger
    Then replug the Pico — no further permission changes needed.

Usage:
    python deploy.py               # deploy everything
    python deploy.py --code-only   # skip frames/, push source files only
"""

import os
import sys
import argparse
import subprocess

DEVICE   = '/dev/ttyACM0'
PICO_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pico')

CODE_FILES = {'epd.py', 'main.py', 'show_animation.py', 'show_image.py'}


def mp(*args, allow_fail=False):
    """Run an mpremote command, exit on failure unless allow_fail is set."""
    cmd = ['mpremote', 'connect', DEVICE] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 and not allow_fail:
        print(f"  Error: {result.stderr.strip()}")
        sys.exit(1)
    return result.returncode == 0


def ensure_dir(remote_path):
    """Create a remote directory, ignoring error if it already exists."""
    mp('mkdir', ':' + remote_path, allow_fail=True)


def copy_file(local_path, remote_path):
    print(f"  {os.path.relpath(local_path, PICO_SRC)} → :{remote_path}")
    mp('cp', local_path, ':' + remote_path)


def deploy(code_only=False):
    if not os.path.exists(DEVICE):
        print(f"Device not found: {DEVICE}")
        print("Check the Pico is connected and the port is correct.")
        sys.exit(1)

    print(f"Deploying to {DEVICE}" + (" (code only)" if code_only else "") + "...\n")

    for root, dirs, files in os.walk(PICO_SRC):
        dirs.sort()
        rel_dir = os.path.relpath(root, PICO_SRC)
        in_frames = rel_dir == 'frames' or rel_dir.startswith('frames' + os.sep)

        if code_only and in_frames:
            dirs.clear()   # don't descend into frames/
            continue

        # Ensure the remote directory exists
        if rel_dir != '.':
            ensure_dir(rel_dir.replace(os.sep, '/'))

        for filename in sorted(files):
            if not filename.endswith('.py') or filename.startswith('_'):
                continue
            if code_only and filename not in CODE_FILES:
                continue

            local_path  = os.path.join(root, filename)
            remote_path = (filename if rel_dir == '.'
                           else rel_dir.replace(os.sep, '/') + '/' + filename)
            copy_file(local_path, remote_path)

    print("\nDone.")


def main():
    parser = argparse.ArgumentParser(description='Deploy files to the Pico.')
    parser.add_argument('--code-only', action='store_true',
                        help='Skip frames/ — only push source .py files')
    args = parser.parse_args()
    deploy(code_only=args.code_only)


if __name__ == '__main__':
    main()

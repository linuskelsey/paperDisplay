# main.py
# Entry point for the e-ink pixel art display.
# Runs automatically on boot via MicroPython's main.py convention.
#
# Startup behaviour:
#   1. Scans frames/img/ for all byte array .py files (alphabetical order)
#   2. Full refresh, then displays the first image found
#   3. Puts the display to sleep — image persists with zero power draw
#
# Byte arrays are produced by convert.py on the host and already incorporate
# the 90° rotation needed for landscape display on the portrait-native panel.
#
# To add a new image:
#   - Draw at 296 × 152 px in Procreate, export as PNG
#   - Run convert/convert.py on the host to produce a .py byte array
#   - Copy the .py file into frames/img/ on the Pico
#   - Reboot — it will be picked up automatically

from show_animation import run

run('twin_orb')

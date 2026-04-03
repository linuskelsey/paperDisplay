# main.py
# Entry point for the e-ink pixel art display.
# Runs automatically when the Pico powers up.
#
# Startup behaviour:
#   1. Full refresh + show first static image (totoro)
#   2. Wait briefly, then switch to animation mode (partial refresh)
#   3. Loop animation frames indefinitely
#
# To add new images/frames:
#   - Run convert.py on your PNG to produce a byte array .py file
#   - Drop the file into pico/frames/
#   - Import it below and add it to IMAGES or ANIMATION_FRAMES

import utime
from epd import EPD

# --- Import your frames ---
from frames.totoro import totoro

# Static images shown on startup (just one for now)
# Add more as: from frames.myimage import myimage
IMAGES = [
    totoro,
]

# Animation frames shown after the static image
# Add each frame in order: from frames.rain_01 import rain_01
ANIMATION_FRAMES = [
    # rain_01,
    # rain_02,
    # rain_03,
]

# How long to show the static image before switching to animation (seconds)
STATIC_DISPLAY_DURATION = 5

# Delay between animation frames (seconds)
# 0.3s is the minimum partial refresh time for this display
FRAME_DELAY = 0.3


def show_static(epd, image):
    """Full refresh and display a static image."""
    epd.init(mode=0)        # full refresh mode
    epd.clear()             # blank the screen cleanly
    utime.sleep_ms(500)
    epd.display(image)


def run_animation(epd, frames):
    """Loop through animation frames indefinitely using partial refresh."""
    epd.init(mode=1)        # partial refresh mode
    index = 0
    while True:
        epd.display_partial(frames[index])
        utime.sleep(FRAME_DELAY)
        index = (index + 1) % len(frames)  # loop back to start


def main():
    epd = EPD()             # initialise display with default pin numbers

    # --- Static image on startup ---
    show_static(epd, IMAGES[0])
    utime.sleep(STATIC_DISPLAY_DURATION)

    # --- Animation loop ---
    if ANIMATION_FRAMES:
        run_animation(epd, ANIMATION_FRAMES)
    else:
        # No animation frames yet — just hold the static image
        # and put the display to sleep to save power
        epd.sleep()


main()

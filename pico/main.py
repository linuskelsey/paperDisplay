# main.py
# Entry point for the e-ink pixel art display.
# Runs automatically when the Pico powers up.
#
# Startup behaviour:
#   1. Scans pico/frames/img/ for all byte array files
#   2. Full refresh and displays the first image found
#
# To add a new image:
#   - Draw in Procreate, export as PNG
#   - Run convert.py on your laptop to produce a byte array .py file
#   - Drop the file into pico/frames/img/
#   - Reboot the Pico — it will be picked up automatically

import utime
import os
from epd import EPD


def discover_frames():
    """
    Scan the frames/img/ directory and return a list of image byte arrays,
    one per file found. Files are loaded in alphabetical order.
    """
    images = []
    try:
        files = sorted(os.listdir('frames/img'))
    except OSError:
        print("frames/img/ directory not found")
        return images

    for filename in files:
        if filename.endswith('.py') and not filename.startswith('_'):
            module_name = filename[:-3]     # strip .py
            try:
                module = __import__('frames.img.' + module_name, None, None, [module_name])
                # The byte array inside the module shares its name with the file
                image = getattr(module, module_name)
                images.append(image)
                print("Loaded: " + module_name)
            except Exception as e:
                print("Failed to load " + module_name + ": " + str(e))

    return images


def show_image(epd, image):
    """Full refresh and display a single image."""
    epd.init(mode=0)
    epd.clear()
    utime.sleep_ms(500)
    epd.display(image)


def main():
    epd = EPD()

    images = discover_frames()

    if not images:
        print("No images found in frames/img/ — nothing to display")
        return

    print(str(len(images)) + " image(s) found")

    # Display the first image and sleep
    show_image(epd, images[0])
    epd.sleep()


main()

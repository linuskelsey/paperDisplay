import os
import random
from epd import EPD


def load_images():
    images = []
    try:
        files = sorted(f for f in os.listdir('frames/img')
                       if f.endswith('.py') and not f.startswith('_'))
    except OSError:
        print("frames/img/ not found")
        return images

    for filename in files:
        module_name = filename[:-3]
        try:
            module = __import__('frames.img.' + module_name, None, None, [module_name])
            images.append(getattr(module, module_name))
            print("Loaded: " + module_name)
        except Exception as e:
            print("Failed: " + module_name + ": " + str(e))

    return images


def run():
    epd = EPD()
    images = load_images()

    if not images:
        print("No images found")
        return

    img = images[random.randint(0, len(images) - 1)]
    print("Displaying image...")
    epd.init(mode=0)
    epd.display_full(img)
    epd.sleep()

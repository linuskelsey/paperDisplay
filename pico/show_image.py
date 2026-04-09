import os
import random
import utime
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


def run(N):
    epd = EPD()
    images = load_images()

    if not images:
        print("No images found")
        return

    epd.init(mode=0)
    i = random.randint(0, len(images) - 1)
    for _ in range(N):
        img = images[i]
        epd.display_full(img)
        utime.sleep_ms(2000)
        i += 1
        i = i % len(images)
    epd.clear()
    epd.sleep()

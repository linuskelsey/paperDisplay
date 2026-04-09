import os
import utime
from epd import EPD

LOOPS = 20


def load_frames(name):
    frames = []
    dir_path = 'frames/ani/' + name
    try:
        files = sorted(f for f in os.listdir(dir_path)
                       if f.endswith('.py') and not f.startswith('_'))
    except OSError:
        print("Animation not found: " + dir_path)
        return frames

    for filename in files:
        module_name = filename[:-3]
        try:
            module = __import__('frames.ani.' + name + '.' + module_name,
                                None, None, [module_name])
            frames.append(getattr(module, module_name))
        except Exception as e:
            print("Failed: " + module_name + ": " + str(e))

    return frames


def run(name):
    epd = EPD()
    frames = load_frames(name)

    if not frames:
        print("No frames loaded for: " + name)
        return

    print(str(len(frames)) + " frames loaded — running " + str(LOOPS) + " loops")

    # Prime with a full refresh so partial has a clean base
    epd.init(mode=0)
    epd.display_full(frames[0])

    # Switch to partial refresh for animation
    epd.init(mode=1)

    for loop in range(LOOPS):
        for frame in frames:
            epd.display_partial(frame)
        print("Loop " + str(loop + 1) + "/" + str(LOOPS))
    
    epd.clear()
    epd.sleep()
    print("Done")

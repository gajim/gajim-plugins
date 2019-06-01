from io import BytesIO
from PIL import Image


def resize_gif(mem, path, resize_to):
    frames, result = extract_and_resize_frames(mem, resize_to)

    if len(frames) == 1:
        frames[0].save(path, optimize=True)
    else:
        frames[0].save(path,
                       optimize=True,
                       save_all=True,
                       append_images=frames[1:],
                       duration=result['duration'],
                       loop=1000)


def analyse_image(mem):
    '''
    Pre-process pass over the image to determine the mode (full or additive).
    Necessary as assessing single frames isn't reliable. Need to know the mode
    before processing all frames.
    '''
    image = Image.open(BytesIO(mem))
    results = {
        'size': image.size,
        'mode': 'full',
        'duration': image.info.get('duration', 0)
    }

    try:
        while True:
            if image.tile:
                tile = image.tile[0]
                update_region = tile[1]
                update_region_dimensions = update_region[2:]
                if update_region_dimensions != image.size:
                    results['mode'] = 'partial'
                    break
            image.seek(image.tell() + 1)
    except EOFError:
        pass
    return results


def extract_and_resize_frames(mem, resize_to):
    result = analyse_image(mem)
    image = Image.open(BytesIO(mem))

    i = 0
    palette = image.getpalette()
    last_frame = image.convert('RGBA')

    frames = []

    try:
        while True:
            '''
            If the GIF uses local colour tables,
            each frame will have its own palette.
            If not, we need to apply the global palette to the new frame.
            '''
            if not image.getpalette():
                image.putpalette(palette)

            new_frame = Image.new('RGBA', image.size)

            '''
            Is this file a "partial"-mode GIF where frames update a region
            of a different size to the entire image?
            If so, we need to construct the new frame by
            pasting it on top of the preceding frames.
            '''
            if result['mode'] == 'partial':
                new_frame.paste(last_frame)

            new_frame.paste(image, (0, 0), image.convert('RGBA'))

            # This method preservs aspect ratio
            new_frame.thumbnail(resize_to, Image.ANTIALIAS)
            frames.append(new_frame)

            i += 1
            last_frame = new_frame
            image.seek(image.tell() + 1)
    except EOFError:
        pass

    return frames, result

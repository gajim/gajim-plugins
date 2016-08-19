from gi.repository import GdkPixbuf
import base64
from io import BytesIO
import os
import sys
import logging
from urllib.parse import quote as urlquote
try:
    from PIL import Image
    pil_available = True
except:
    pil_available = False

log = logging.getLogger('gajim.plugin_system.httpupload.thumbnail')

def scale_down_to(pixbuf, size):
    # Creates a pixbuf that fits in the specified square of sizexsize
    # while preserving the aspect ratio
    # Returns scaled_pixbuf
    image_width = pixbuf.get_width()
    image_height = pixbuf.get_height()

    if image_width > image_height:
        if image_width > size:
            image_height = int(size / float(image_width) * image_height)
            image_width = int(size)
    else:
        if image_height > size:
            image_width = int(size / float(image_height) * image_width)
            image_height = int(size)

    crop_pixbuf = pixbuf.scale_simple(image_width, image_height, GdkPixbuf.InterpType.BILINEAR)
    return crop_pixbuf


max_thumbnail_size = 2048
max_thumbnail_dimension = 160
base64_size_factor = 4/3
def thumbnail(path_to_file):
    """
    Generates a JPEG thumbnail and base64-encodes, ensuring that the encoded
    size is less than max_thumbnail_size bytes. If this is not possible, returns
    None.
    """
    thumb = None
    quality_steps = (100, 80, 60, 50, 40, 35, 30, 25, 23, 20, 18, 15, 13, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1)
    # If the whole file is small enough, we'll just use that as a thumbnail
    # without downsampling.
    if os.path.getsize(path_to_file) * base64_size_factor < max_thumbnail_size:
        with open(path_to_file, 'rb') as content_file:
            thumb = urlquote(base64.standard_b64encode(content_file.read()), '')
            log.info("Image small enough (%d bytes), not resampling" % len(thumb))
            return thumb
    elif pil_available:
        log.info("PIL available, using it for image downsampling")
        try:
            for quality in quality_steps:
                thumb = Image.open(path_to_file)
                thumb.thumbnail((max_thumbnail_dimension, max_thumbnail_dimension), Image.ANTIALIAS)
                output = BytesIO()
                thumb.save(output, format='JPEG', quality=quality, optimize=True)
                thumb = output.getvalue()
                output.close()
                thumb = urlquote(base64.standard_b64encode(thumb), '')
                log.debug("pil thumbnail jpeg quality %d produces an image of size %d...", quality, len(thumb))
                if len(thumb) < max_thumbnail_size:
                    log.debug("Size is acceptable.")
                    return thumb
        except:
            log.info("Exception occurred during PIL downsampling", exc_info=sys.exc_info())
            thumb = None
    # If we haven't returned by now we couldn't use PIL for one reason or
    # another, so let's pass on to GdkPixbuf
    log.info("using GdkPixBuf for image downsampling")
    temp_file = None
    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(path_to_file)
        scaled_pb = scale_down_to(pixbuf, max_thumbnail_dimension)
        for quality in quality_steps:
            success, thumb_raw = scaled_pb.save_to_bufferv("jpeg", ["quality"], [str(quality)])
            log.debug("gdkpixbuf thumbnail jpeg quality %d produces an image of size %d...",
                      quality,
                      len(thumb_raw) * base64_size_factor)
            if len(thumb_raw) * base64_size_factor < max_thumbnail_size:
                log.debug("Size is acceptable.")
                return urlquote(base64.standard_b64encode(thumb_raw))
    except:
        log.info("Exception occurred during GdkPixbuf downsampling, not providing thumbnail", exc_info=sys.exc_info())
        return None
    log.info("No acceptably small thumbnail was generated.")

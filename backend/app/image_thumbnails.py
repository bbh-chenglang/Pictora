from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps

THUMBNAIL_MAX_SIZE = 512
THUMBNAIL_WEBP_QUALITY = 80


class ThumbnailGenerationError(Exception):
    pass


@dataclass(frozen=True)
class WebPThumbnail:
    data: bytes
    width: int
    height: int


def create_webp_thumbnail(image_data: bytes) -> WebPThumbnail:
    try:
        with Image.open(BytesIO(image_data)) as source:
            image = ImageOps.exif_transpose(source)
            image.thumbnail(
                (THUMBNAIL_MAX_SIZE, THUMBNAIL_MAX_SIZE),
                Image.Resampling.LANCZOS,
            )
            has_alpha = "A" in image.getbands() or (
                image.mode == "P" and "transparency" in image.info
            )
            image = image.convert("RGBA" if has_alpha else "RGB")
            output = BytesIO()
            image.save(
                output,
                format="WEBP",
                quality=THUMBNAIL_WEBP_QUALITY,
                method=4,
            )
            return WebPThumbnail(
                data=output.getvalue(),
                width=image.width,
                height=image.height,
            )
    except (Image.DecompressionBombError, OSError, ValueError) as exc:
        raise ThumbnailGenerationError("Unable to generate image thumbnail") from exc

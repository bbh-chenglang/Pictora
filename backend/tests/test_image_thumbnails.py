from io import BytesIO

from PIL import Image

from app.image_thumbnails import create_webp_thumbnail


def test_create_webp_thumbnail_resizes_longest_side_and_encodes_webp() -> None:
    source = BytesIO()
    Image.new("RGB", (1024, 512), (20, 80, 160)).save(source, format="PNG")

    thumbnail = create_webp_thumbnail(source.getvalue())

    assert (thumbnail.width, thumbnail.height) == (512, 256)
    with Image.open(BytesIO(thumbnail.data)) as decoded:
        assert decoded.format == "WEBP"
        assert decoded.size == (512, 256)

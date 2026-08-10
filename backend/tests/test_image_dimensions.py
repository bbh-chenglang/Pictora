from fractions import Fraction

import pytest

from app.image_dimensions import OUTPUT_DIMENSIONS_BY_RESOLUTION, output_size


ASPECT_RATIOS = {
    "1:1": Fraction(1, 1),
    "3:2": Fraction(3, 2),
    "2:3": Fraction(2, 3),
    "9:16": Fraction(9, 16),
    "16:9": Fraction(16, 9),
}


@pytest.mark.parametrize(
    ("resolution", "aspect_ratio", "expected"),
    [
        (resolution, aspect_ratio, dimensions)
        for resolution, options in OUTPUT_DIMENSIONS_BY_RESOLUTION.items()
        for aspect_ratio, dimensions in options.items()
    ],
)
def test_output_dimensions_follow_gpt_image_2_constraints(
    resolution: str,
    aspect_ratio: str,
    expected: tuple[int, int],
) -> None:
    width, height = expected

    assert output_size(aspect_ratio, resolution, "auto") == f"{width}x{height}"
    assert Fraction(width, height) == ASPECT_RATIOS[aspect_ratio]
    assert width % 16 == 0
    assert height % 16 == 0
    assert max(width, height) <= 3840
    assert 655_360 <= width * height <= 8_294_400

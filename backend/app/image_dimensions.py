OUTPUT_DIMENSIONS_BY_RESOLUTION: dict[str, dict[str, tuple[int, int]]] = {
    "1K": {
        "1:1": (1024, 1024),
        "3:2": (1536, 1024),
        "2:3": (1024, 1536),
        "9:16": (720, 1280),
        "16:9": (1280, 720),
    },
    "2K": {
        "1:1": (2048, 2048),
        "3:2": (2016, 1344),
        "2:3": (1344, 2016),
        "9:16": (1152, 2048),
        "16:9": (2048, 1152),
    },
    "4K": {
        "1:1": (2880, 2880),
        "3:2": (3504, 2336),
        "2:3": (2336, 3504),
        "9:16": (2160, 3840),
        "16:9": (3840, 2160),
    },
}


def output_dimensions(aspect_ratio: str | None, resolution: str | None) -> tuple[int, int] | None:
    if aspect_ratio is None or resolution is None:
        return None
    return OUTPUT_DIMENSIONS_BY_RESOLUTION[resolution][aspect_ratio]


def output_size(aspect_ratio: str | None, resolution: str | None, fallback: str) -> str:
    dimensions = output_dimensions(aspect_ratio, resolution)
    if dimensions is None:
        return fallback
    return f"{dimensions[0]}x{dimensions[1]}"

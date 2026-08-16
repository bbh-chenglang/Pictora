import re
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from app.schemas.generate import GenerateRequest


ProviderType = Literal["gpt", "gemini", "grok"]


class CapabilityOption(BaseModel):
    value: str
    label: str


class SizeConstraints(BaseModel):
    width_multiple: int
    height_multiple: int
    max_long_edge: int
    max_aspect_ratio: float
    min_pixels: int
    max_pixels: int


class ModelCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider_type: ProviderType
    model: str
    label: str
    max_output_count: int = Field(ge=1, le=10)
    max_reference_images: int = Field(ge=0)
    sizes: tuple[CapabilityOption, ...] = ()
    size_constraints: SizeConstraints | None = None
    aspect_ratios: tuple[str, ...] = ()
    resolutions: tuple[str, ...] = ()
    qualities: tuple[CapabilityOption, ...] = ()
    output_formats: tuple[str, ...] = ()
    backgrounds: tuple[str, ...] = ()
    supports_output_compression: bool = False
    moderation_levels: tuple[str, ...] = ()
    default_size: str | None = None
    default_aspect_ratio: str | None = None
    default_resolution: str | None = None
    default_quality: str = "auto"


class UnsupportedModelError(ValueError):
    def __init__(self, provider_type: str, model: str) -> None:
        self.provider_type = provider_type
        self.model = model
        super().__init__(f"Model '{model}' is not registered for provider '{provider_type}'")


class UnsupportedModelParameterError(ValueError):
    pass


STANDARD_GPT_SIZES = (
    CapabilityOption(value="auto", label="自动"),
    CapabilityOption(value="1024x1024", label="正方形"),
    CapabilityOption(value="1536x1024", label="横向"),
    CapabilityOption(value="1024x1536", label="纵向"),
)
GPT_IMAGE_2_SIZES = (
    *STANDARD_GPT_SIZES,
    CapabilityOption(value="2048x2048", label="2K 正方形"),
    CapabilityOption(value="2048x1152", label="2K 横向"),
    CapabilityOption(value="1152x2048", label="2K 纵向"),
    CapabilityOption(value="3840x2160", label="4K 横向"),
    CapabilityOption(value="2160x3840", label="4K 纵向"),
)
STANDARD_QUALITIES = (
    CapabilityOption(value="auto", label="自动"),
    CapabilityOption(value="low", label="低"),
    CapabilityOption(value="medium", label="中"),
    CapabilityOption(value="high", label="高"),
)
GROK_2_QUALITIES = (
    CapabilityOption(value="low", label="低"),
    CapabilityOption(value="medium", label="中"),
)
STANDARD_GEMINI_RATIOS = (
    "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9",
)
GEMINI_31_RATIOS = (*STANDARD_GEMINI_RATIOS, "1:4", "1:8", "4:1", "8:1")
GROK_RATIOS = (
    "auto", "1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3",
    "2:1", "1:2", "19.5:9", "9:19.5", "20:9", "9:20",
)


def _gpt_capability(model: str, label: str, *, image_2: bool = False) -> ModelCapabilities:
    return ModelCapabilities(
        provider_type="gpt",
        model=model,
        label=label,
        max_output_count=4,
        max_reference_images=16,
        sizes=GPT_IMAGE_2_SIZES if image_2 else STANDARD_GPT_SIZES,
        size_constraints=SizeConstraints(
            width_multiple=16,
            height_multiple=16,
            max_long_edge=3840,
            max_aspect_ratio=3,
            min_pixels=655_360,
            max_pixels=8_294_400,
        ) if image_2 else None,
        qualities=STANDARD_QUALITIES,
        output_formats=("png", "jpeg", "webp"),
        backgrounds=("auto", "opaque") if image_2 else ("auto", "opaque", "transparent"),
        supports_output_compression=True,
        moderation_levels=("auto", "low"),
        default_size="auto",
        default_quality="auto",
    )


MODEL_CAPABILITIES = (
    _gpt_capability("gpt-image-2", "GPT Image 2", image_2=True),
    _gpt_capability("gpt-image-1.5", "GPT Image 1.5"),
    _gpt_capability("gpt-image-1", "GPT Image 1"),
    _gpt_capability("gpt-image-1-mini", "GPT Image 1 Mini"),
    ModelCapabilities(
        provider_type="gemini",
        model="gemini-3.1-flash-image",
        label="Gemini 3.1 Flash Image",
        max_output_count=4,
        max_reference_images=14,
        aspect_ratios=GEMINI_31_RATIOS,
        resolutions=("1K", "2K", "4K"),
        default_aspect_ratio="1:1",
        default_resolution="1K",
    ),
    ModelCapabilities(
        provider_type="gemini",
        model="gemini-3-pro-image-preview",
        label="Gemini 3 Pro Image Preview",
        max_output_count=4,
        max_reference_images=14,
        aspect_ratios=STANDARD_GEMINI_RATIOS,
        resolutions=("1K", "2K", "4K"),
        default_aspect_ratio="1:1",
        default_resolution="1K",
    ),
    ModelCapabilities(
        provider_type="gemini",
        model="gemini-3.1-flash-lite-image-preview",
        label="Gemini 3.1 Flash Lite Image Preview",
        max_output_count=4,
        max_reference_images=14,
        aspect_ratios=STANDARD_GEMINI_RATIOS,
        default_aspect_ratio="1:1",
    ),
    ModelCapabilities(
        provider_type="gemini",
        model="gemini-2.5-flash-image",
        label="Gemini 2.5 Flash Image",
        max_output_count=4,
        max_reference_images=3,
        aspect_ratios=STANDARD_GEMINI_RATIOS,
        default_aspect_ratio="1:1",
    ),
    ModelCapabilities(
        provider_type="grok",
        model="grok-imagine-image",
        label="Grok Imagine Image",
        max_output_count=4,
        max_reference_images=3,
        aspect_ratios=GROK_RATIOS,
        resolutions=("1K", "2K"),
        default_aspect_ratio="auto",
        default_resolution="1K",
    ),
    ModelCapabilities(
        provider_type="grok",
        model="grok-imagine-image-2.0",
        label="Grok Imagine Image 2.0",
        max_output_count=4,
        max_reference_images=3,
        aspect_ratios=GROK_RATIOS,
        resolutions=("1K", "2K"),
        qualities=GROK_2_QUALITIES,
        default_aspect_ratio="auto",
        default_resolution="1K",
        default_quality="medium",
    ),
)

_CAPABILITIES_BY_KEY = {
    (capability.provider_type, capability.model.casefold()): capability
    for capability in MODEL_CAPABILITIES
}

DEFAULT_MODEL_BY_PROVIDER: dict[ProviderType, str] = {
    "gpt": "gpt-image-2",
    "gemini": "gemini-3.1-flash-image",
    "grok": "grok-imagine-image",
}


def normalize_provider_type(provider: str) -> ProviderType:
    normalized = provider.strip().casefold()
    if normalized in {"openai", "compatible", "gpt"}:
        return "gpt"
    if normalized in {"gemini", "grok"}:
        return normalized
    raise UnsupportedModelError(normalized, "")


def get_model_capabilities(provider: str, model: str) -> ModelCapabilities:
    provider_type = normalize_provider_type(provider)
    normalized_model = model.strip().casefold()
    try:
        return _CAPABILITIES_BY_KEY[(provider_type, normalized_model)]
    except KeyError:
        raise UnsupportedModelError(provider_type, model.strip()) from None


def supported_models(provider: str) -> tuple[str, ...]:
    provider_type = normalize_provider_type(provider)
    return tuple(
        capability.model
        for capability in MODEL_CAPABILITIES
        if capability.provider_type == provider_type
    )


def filter_supported_model_ids(provider: str, model_ids: list[str]) -> list[str]:
    provider_type = normalize_provider_type(provider)
    registered = {
        capability.model.casefold(): capability.model
        for capability in MODEL_CAPABILITIES
        if capability.provider_type == provider_type
    }
    return [registered[model_id.strip().removeprefix("models/").casefold()]
            for model_id in model_ids
            if model_id.strip().removeprefix("models/").casefold() in registered]


def normalize_generation_request(request: "GenerateRequest") -> "GenerateRequest":
    capability = get_model_capabilities(request.provider, request.model)
    if request.count > capability.max_output_count:
        raise UnsupportedModelParameterError(
            f"{capability.model} supports at most {capability.max_output_count} images per request"
        )

    updates: dict[str, object] = {"model": capability.model}
    size = request.size
    if capability.sizes:
        size = size or capability.default_size
        known_sizes = {option.value for option in capability.sizes}
        if size not in known_sizes:
            constraints = capability.size_constraints
            match = re.fullmatch(r"(\d+)x(\d+)", size or "")
            if constraints is None or match is None:
                raise UnsupportedModelParameterError(f"{capability.model} does not support size '{size}'")
            width, height = map(int, match.groups())
            short_edge, long_edge = sorted((width, height))
            pixels = width * height
            if (
                width % constraints.width_multiple
                or height % constraints.height_multiple
                or long_edge > constraints.max_long_edge
                or long_edge > short_edge * constraints.max_aspect_ratio
                or pixels < constraints.min_pixels
                or pixels > constraints.max_pixels
            ):
                raise UnsupportedModelParameterError(f"{capability.model} does not support size '{size}'")
        updates["size"] = size
        updates["aspect_ratio"] = None
        updates["resolution"] = None
    else:
        aspect_ratio = request.aspect_ratio or capability.default_aspect_ratio
        if aspect_ratio not in capability.aspect_ratios:
            raise UnsupportedModelParameterError(
                f"{capability.model} does not support aspect ratio '{aspect_ratio}'"
            )
        resolution = request.resolution or capability.default_resolution
        if resolution is not None and resolution not in capability.resolutions:
            raise UnsupportedModelParameterError(
                f"{capability.model} does not support resolution '{resolution}'"
            )
        updates.update(size=None, aspect_ratio=aspect_ratio, resolution=resolution)

    if capability.qualities:
        quality = capability.default_quality if request.detail == "auto" else request.detail
        if quality not in {option.value for option in capability.qualities}:
            raise UnsupportedModelParameterError(
                f"{capability.model} does not support quality '{quality}'"
            )
        updates["detail"] = quality
    else:
        if request.detail != "auto":
            raise UnsupportedModelParameterError(
                f"{capability.model} does not support quality '{request.detail}'"
            )
        updates["detail"] = "auto"

    for field, supported in (
        ("output_format", capability.output_formats),
        ("background", capability.backgrounds),
        ("moderation", capability.moderation_levels),
    ):
        value = getattr(request, field)
        if value is not None and value not in supported:
            raise UnsupportedModelParameterError(
                f"{capability.model} does not support {field} '{value}'"
            )
        updates[field] = value if supported else None

    output_compression = request.output_compression
    if output_compression is not None and not capability.supports_output_compression:
        raise UnsupportedModelParameterError(
            f"{capability.model} does not support output compression"
        )
    if request.output_format == "png":
        output_compression = None
    if request.background == "transparent" and request.output_format == "jpeg":
        raise UnsupportedModelParameterError("Transparent backgrounds require PNG or WebP output")
    updates["output_compression"] = output_compression
    return request.model_copy(update=updates)

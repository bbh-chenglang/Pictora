import asyncio
import hashlib
import re
import time

import httpx

from app.video.repository import VideoError

# Video model ids encode capabilities using the confirmed naming convention:
#   <model-name>-<image/video/audio limits>-<max resolution>
# For example, seedance-2.0-933-720P means 9 images, 3 videos,
# 3 audios, with a maximum output resolution of 720p.
KNOWN_MODELS = (
    "seedance-2.0-933-720P（秒）",
    "seedance-2.0-fast-933-720P（次）",
    "seedance-2.0-mini-903-720P（次）",
    "seedance-2.5-301010-1K（秒）",
    "minimax-h3-933-2K（次）",
)
RULES = {name: (None, None, None) for name in KNOWN_MODELS}

_RESOLUTION_CODE = re.compile(r"(?P<value>[1-9][0-9]*)(?P<unit>[KkPp])$")


def _resolution_from_code(code: str) -> str | None:
    match = _RESOLUTION_CODE.fullmatch(code)
    if not match:
        return None
    value, unit = int(match.group("value")), match.group("unit").upper()
    if unit == "P" and value < 480:
        return None
    return f"{value}k" if unit == "K" else f"{value}p"


def _limits_from_code(code: str) -> dict[str, int] | None:
    # Three one-digit limits (933), or three two-digit limits (301010).
    if not re.fullmatch(r"(?:[0-9]{3}|[0-9]{6})", code):
        return None
    width = len(code) // 3
    return {kind: int(code[index * width:(index + 1) * width])
            for index, kind in enumerate(("image", "video", "audio"))}


def parse_model_capabilities(name: str) -> tuple[str, dict[str, int], str] | None:
    """Parse the capability suffix encoded in a video model id.

    The optional billing suffix in parentheses is ignored. Unknown model names
    are accepted as long as both capability codes are present.
    """
    if not isinstance(name, str):
        return None
    clean = re.sub(r"\s*[（(](?:秒|次)[）)]\s*$", "", name.strip())
    parts = clean.rsplit("-", 2)
    if len(parts) != 3:
        return None
    model_name, limits_code, resolution_code = parts
    limits = _limits_from_code(limits_code)
    resolution = _resolution_from_code(resolution_code)
    if not model_name or limits is None or resolution is None:
        return None
    return model_name, limits, resolution


def _resolutions(max_resolution: str) -> tuple[str, ...]:
    # The upstream API accepts only these values. A model-name suffix such as
    # 1K or 2K must never become a literal resolution request parameter.
    if max_resolution.endswith("p"):
        maximum = int(max_resolution[:-1])
        return tuple(f"{height}p" for height in (480, 720, 1080) if height <= maximum)
    return ("480p", "720p", "1080p")


def _model(
    name: str,
    resolutions: tuple[str, ...] | None = None,
    default_duration: int = 5,
    reference_limits: dict[str, int] | None = None,
) -> dict:
    parsed = parse_model_capabilities(name)
    if parsed:
        _, parsed_limits, max_resolution = parsed
        reference_limits = parsed_limits
        resolutions = _resolutions(max_resolution)
    resolutions = resolutions or ("720p",)
    default_resolution = "720p" if "720p" in resolutions else resolutions[0]
    if name.startswith("seedance-2.0-mini-") and "480p" in resolutions:
        default_resolution = "480p"
    limits = {kind: None for kind in ("image", "video", "audio")}
    if reference_limits:
        limits.update(reference_limits)
    return {
        "id": name,
        "default_duration": default_duration,
        "default_resolution": default_resolution,
        "default_ratio": "16:9",
        "ratios": ["16:9", "9:16", "1:1"],
        "durations_by_resolution": {resolution: list(range(1, 16)) for resolution in resolutions},
        "reference_limits": limits,
        "max_total_materials": None,
        "max_video_duration_seconds": None,
    }


def bundled_models() -> list[dict]:
    return [_model(name) for name in KNOWN_MODELS]


def live_model(name: str | None) -> dict | None:
    if not isinstance(name, str) or not name.strip() or len(name) > 160:
        return None
    return _model(name)


class VideoCatalog:
    def __init__(self, base_url, transport=None):
        self.base_url, self.transport = base_url.rstrip("/"), transport
        self.models, self.source, self.expires, self.key_digest = bundled_models(), "bundled_snapshot_2026-10-10", 0.0, None
        self.lock = asyncio.Lock()

    @staticmethod
    def _digest(key):
        return hashlib.sha256(key.encode()).hexdigest()[:16] if key else None

    async def get(self, key=None, force=False):
        digest = self._digest(key)
        if not force and digest == self.key_digest and time.monotonic() < self.expires:
            return self.models
        if key is None:
            self.key_digest, self.expires = None, float("inf")
            return self.models
        async with self.lock:
            if not force and digest == self.key_digest and time.monotonic() < self.expires:
                return self.models
            try:
                async with httpx.AsyncClient(transport=self.transport, timeout=15, follow_redirects=False, trust_env=False) as client:
                    response = await client.get(self.base_url + "/v1/models", headers={"Authorization": "Bearer " + key, "Accept": "application/json"})
                    response.raise_for_status()
                    data = response.json()
                rows = data.get("data") if isinstance(data, dict) else None
                if not isinstance(rows, list):
                    raise ValueError("Invalid model list")
                fresh, seen = [], set()
                for row in rows:
                    model = live_model(row.get("id") if isinstance(row, dict) else None)
                    if model is not None and model["id"] not in seen:
                        seen.add(model["id"])
                        fresh.append(model)
                if not fresh:
                    raise ValueError("Empty model list")
                self.models, self.source, self.key_digest, self.expires = fresh, "live_catalog", digest, time.monotonic() + 600
            except (httpx.HTTPError, ValueError, TypeError, AttributeError):
                self.source = "cached_live_catalog" if self.key_digest == digest and self.source == "live_catalog" else "bundled_snapshot_2026-10-10"
                if self.key_digest != digest:
                    self.models = bundled_models()
                self.key_digest, self.expires = digest, time.monotonic() + 60
        return self.models

    async def normalize(self, request, materials, key=None):
        model = next((m for m in await self.get(key) if m["id"] == request.model), None)
        if model is None:
            raise VideoError("video_model_unsupported", "所选视频模型未出现在当前 API Key 的模型列表中", 422)
        resolution = request.resolution or model["default_resolution"]
        duration = request.duration if request.duration is not None else model["default_duration"]
        ratio = request.ratio or model["default_ratio"]
        if duration not in model["durations_by_resolution"].get(resolution, []) or ratio not in model["ratios"]:
            raise VideoError("video_parameters_invalid", "时长、分辨率或比例不在该模型的有效档位内", 422)
        names, sources, content = set(), set(), [{"type": "text", "text": request.prompt}]
        counts = {kind: 0 for kind in ("image", "video", "audio")}
        for material in materials:
            if material["name"] in names:
                raise VideoError("video_material_name_duplicate", "素材名称必须互不相同", 422)
            if material["url"] in sources:
                raise VideoError("video_material_duplicate", "不要重复提交同一个素材", 422)
            kind = material["type"]
            counts[kind] += 1
            limit = model["reference_limits"].get(kind)
            if limit is None:
                raise VideoError("video_material_unsupported", "该素材类型的能力尚未确认", 422)
            if counts[kind] > limit:
                label = {"image": "图片", "video": "视频", "audio": "音频"}[kind]
                raise VideoError("video_material_limit_exceeded", f"{label}素材最多支持 {limit} 个", 422)
            names.add(material["name"])
            sources.add(material["url"])
            item = {"type": kind + "_url", kind + "_url": {"url": material["url"]}, "role": "reference_" + kind}
            if material["name"]:
                item["name"] = material["name"]
            content.append(item)
        return {"model": request.model, "duration": duration, "resolution": resolution, "ratio": ratio, "content": content}

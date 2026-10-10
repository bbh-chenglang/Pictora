import asyncio
import hashlib
import time
import httpx
from app.video.repository import VideoError

KNOWN_MODELS = {
    "seedance-2.0-933-720P（秒）": (("720p",), 5),
    "seedance-2.0-fast-933-720P（次）": (("720p",), 5),
    "seedance-2.5-301010-1K（秒）": (("480p", "720p", "1080p"), 5),
    "minimax-h3-933-2K（次）": (("480p", "720p", "1080p"), 5),
}
RULES = {name: (None, None, None) for name in KNOWN_MODELS}

def _model(name, resolutions=("720p",), default_duration=5):
    return {"id": name, "default_duration": default_duration, "default_resolution": "720p" if "720p" in resolutions else resolutions[0], "default_ratio": "16:9", "ratios": ["16:9", "9:16", "1:1"], "durations_by_resolution": {r: list(range(1, 16)) for r in resolutions}, "reference_limits": {"image": None, "video": None, "audio": None}, "max_total_materials": None, "max_video_duration_seconds": None}

def bundled_models(): return [_model(name, resolutions, default) for name, (resolutions, default) in KNOWN_MODELS.items()]
def live_model(name):
    if not isinstance(name, str) or not name.strip() or len(name) > 160: return None
    resolutions, default = KNOWN_MODELS.get(name, (("720p",), 5))
    return _model(name, resolutions, default)

class VideoCatalog:
    def __init__(self, base_url, transport=None):
        self.base_url, self.transport = base_url.rstrip("/"), transport
        self.models, self.source, self.expires, self.key_digest = bundled_models(), "bundled_snapshot_2026-10-10", 0.0, None
        self.lock = asyncio.Lock()
    @staticmethod
    def _digest(key): return hashlib.sha256(key.encode()).hexdigest()[:16] if key else None
    async def get(self, key=None, force=False):
        digest = self._digest(key)
        if not force and digest == self.key_digest and time.monotonic() < self.expires: return self.models
        if key is None:
            self.key_digest, self.expires = None, float("inf")
            return self.models
        async with self.lock:
            if not force and digest == self.key_digest and time.monotonic() < self.expires: return self.models
            try:
                async with httpx.AsyncClient(transport=self.transport, timeout=15, follow_redirects=False, trust_env=False) as client:
                    response = await client.get(self.base_url + "/v1/models", headers={"Authorization": "Bearer " + key, "Accept": "application/json"})
                    response.raise_for_status(); data = response.json()
                rows = data.get("data") if isinstance(data, dict) else None
                if not isinstance(rows, list): raise ValueError("Invalid model list")
                fresh, seen = [], set()
                for row in rows:
                    model = live_model(row.get("id") if isinstance(row, dict) else None)
                    if model is not None and model["id"] not in seen: seen.add(model["id"]); fresh.append(model)
                if not fresh: raise ValueError("Empty model list")
                self.models, self.source, self.key_digest, self.expires = fresh, "live_catalog", digest, time.monotonic() + 600
            except (httpx.HTTPError, ValueError, TypeError, AttributeError):
                self.source = "cached_live_catalog" if self.key_digest == digest and self.source == "live_catalog" else "bundled_snapshot_2026-10-10"
                if self.key_digest != digest:
                    self.models = bundled_models()
                self.key_digest, self.expires = digest, time.monotonic() + 60
        return self.models
    async def normalize(self, request, materials, key=None):
        model = next((m for m in await self.get(key) if m["id"] == request.model), None)
        if model is None: raise VideoError("video_model_unsupported", "所选视频模型未出现在当前 API Key 的模型列表中", 422)
        resolution, duration, ratio = request.resolution or model["default_resolution"], request.duration if request.duration is not None else model["default_duration"], request.ratio or model["default_ratio"]
        if duration not in model["durations_by_resolution"].get(resolution, []) or ratio not in model["ratios"]: raise VideoError("video_parameters_invalid", "时长、分辨率或比例不在该模型的有效档位内", 422)
        names, sources, content = set(), set(), [{"type": "text", "text": request.prompt}]
        for material in materials:
            if material["name"] in names: raise VideoError("video_material_name_duplicate", "素材名称必须互不相同", 422)
            if material["url"] in sources: raise VideoError("video_material_duplicate", "不要重复提交同一个素材", 422)
            names.add(material["name"]); sources.add(material["url"])
            kind = material["type"]
            item = {"type": kind + "_url", kind + "_url": {"url": material["url"]}, "role": "reference_" + kind}
            if material["name"]: item["name"] = material["name"]
            content.append(item)
        return {"model": request.model, "duration": duration, "resolution": resolution, "ratio": ratio, "content": content}

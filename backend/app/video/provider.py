import asyncio
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import time
from urllib.parse import quote, urlsplit

import httpx

from app.video.network import https_url
from app.video.repository import VideoError
from app.video.errors import failure_details, failure_summary

TASKS_PATH = "/api/v3/contents/generations/tasks"

def retry_after(value, default):
    if not value:
        return default
    try:
        if value.isdigit(): return max(0, float(value))
        date = parsedate_to_datetime(value)
        if date.tzinfo is None: date = date.replace(tzinfo=timezone.utc)
        return max(0, (date - datetime.now(timezone.utc)).total_seconds())
    except (ValueError, TypeError, OverflowError): return default

class UnavailableVideoProvider:
    def __init__(self, error): self.error = error
    async def unavailable(self, *args, **kwargs): raise self.error
    create = query = content_url = test_key = unavailable

class VideoProvider:
    def __init__(self, settings, transport=None):
        self.settings = settings
        self.base = https_url(settings.video_api_base_url).rstrip("/")
        parts = urlsplit(self.base)
        if parts.path or parts.query:
            raise VideoError("video_base_invalid", "视频服务地址必须为 HTTPS 根地址，不能包含路径或查询参数", 503)
        self.transport = transport

    async def request(self, method, path, key, payload=None, deadline=None):
        deadline = deadline if deadline is not None else time.monotonic() + 120
        for attempt in range(5):
            remaining = deadline - time.monotonic()
            if remaining <= 0: raise VideoError("video_poll_timeout", "本轮查询等待已结束，请稍后恢复", 504)
            try:
                async with httpx.AsyncClient(transport=self.transport, timeout=httpx.Timeout(min(60, remaining), connect=min(15, remaining)), follow_redirects=False, trust_env=False) as client:
                    async with asyncio.timeout(remaining):
                        response = await client.request(method, self.base + path, headers={"Authorization": "Bearer " + key, "Accept": "application/json", **({"Content-Type": "application/json"} if payload is not None else {})}, json=payload)
                delay = retry_after(response.headers.get("retry-after"), max(0.1, self.settings.video_poll_interval) * (2 ** attempt))
                if method == "GET" and (response.status_code == 429 or response.status_code >= 500) and attempt < 4:
                    if time.monotonic() + delay >= deadline: raise VideoError("video_poll_timeout", "自动等待已结束，请稍后恢复查询；上游任务可能仍在执行", 504)
                    await asyncio.sleep(delay); continue
                return response
            except (httpx.RequestError, TimeoutError):
                if method != "GET" or attempt == 4: raise VideoError("video_network", "视频服务网络异常，请核对原任务，不要重复生成", 502) from None
                delay = max(0.1, self.settings.video_poll_interval) * (2 ** attempt)
                if time.monotonic() + delay >= deadline: raise VideoError("video_poll_timeout", "等待已结束，请恢复查询，不要重新生成", 504) from None
                await asyncio.sleep(delay)
        raise VideoError("video_network", "视频查询重试耗尽", 502)

    @staticmethod
    def json(response, key=None, stage="query"):
        if response.status_code >= 400:
            code = "video_auth" if response.status_code in (401, 403) else "video_upstream_http"
            details = VideoProvider.error_details(response, key, stage)
            raise VideoError(code, failure_summary(details), response.status_code if response.status_code in (400,401,403,404,422,429) else 502, details)
        try:
            data = response.json()
            if not isinstance(data, dict): raise ValueError()
            return data
        except ValueError: raise VideoError("video_response_invalid", "视频服务响应格式无效", 502) from None

    @staticmethod
    def error_details(response, key, stage):
        try:
            data = response.json()
        except ValueError:
            data = {}
        return failure_details(data, stage, secret=key, http_status=response.status_code,
                               request_id=response.headers.get("x-request-id"))

    async def create(self, key, payload):
        response = await self.request("POST", TASKS_PATH, key, payload)
        if 400 <= response.status_code < 500:
            details = self.error_details(response, key, "submission")
            raise VideoError("video_submit_rejected", failure_summary(details), response.status_code, details)
        if response.status_code >= 300: raise VideoError("video_submission_unknown", "视频提交结果不确定，请核对控制台，不要自动重新生成", 502)
        return self.json(response, key, "submission")

    async def query(self, key, task_id, deadline=None):
        return self.json(await self.request("GET", TASKS_PATH + "/" + quote(task_id, safe=""), key, deadline=deadline), key)

    async def content_url(self, key, task_id, deadline=None):
        data = await self.query(key, task_id, deadline)
        content = data.get("content")
        url = content.get("video_url") if isinstance(content, dict) else None
        if not isinstance(url, str) or not url.strip(): raise VideoError("video_content_not_ready", "成功响应缺少视频地址，请稍后重试保存", 502)
        return https_url(url)

    async def test_key(self, key):
        data = self.json(await self.request("GET", "/v1/models", key), key)
        return {"connected": True, "models": [item["id"] for item in data.get("data", []) if isinstance(item, dict) and isinstance(item.get("id"), str)], "message": "已通过非付费模型查询验证；具体模型权限及额度仍以上游为准"}

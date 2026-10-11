"""Shared public diagnostics; never retain keys or signed media URLs."""
import re


def safe_text(value, secret=None, limit=2000):
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return None
    text = str(value)
    if secret:
        text = text.replace(secret, "[redacted]")
    text = re.sub(r"https?://[^\s\"<>]+", "[素材链接已隐藏]", text, flags=re.I)
    text = re.sub(r"(?i)\bBearer\s+[^\s\",;]+", "Bearer [redacted]", text)
    text = re.sub(r"(?i)\b(?:sk|xai)-[A-Za-z0-9_-]+", "[redacted]", text)
    text = re.sub(r"(?i)\b(api[_ -]?key|authorization|access[_ -]?token|token)(\s*[:=]\s*)[\"']?[^\s,\"';]+",
                  lambda m: m.group(1) + m.group(2) + "[redacted]", text)
    return text[:limit].strip() or None


def _message(value):
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for name in ("error", "message", "detail", "msg", "failure_reason"):
            found = _message(value.get(name))
            if found:
                return found
    if isinstance(value, list):
        return "; ".join(filter(None, (_message(item) for item in value[:3]))) or None
    return None


def failure_details(data, stage, *, secret=None, http_status=None, request_id=None, media="video"):
    data = data if isinstance(data, dict) else {}
    error = data.get("error")
    source = error if isinstance(error, dict) else data
    details = {"stage": stage}
    parameter = source.get("param") or source.get("parameter")
    if not parameter and isinstance(data.get("detail"), list):
        parameter = "; ".join(".".join(str(p) for p in item["loc"]) for item in data["detail"][:3]
                              if isinstance(item, dict) and isinstance(item.get("loc"), list))
    for field, value in (
        ("upstream_code", source.get("code") or source.get("type")),
        ("upstream_message", _message(data)), ("parameter", parameter),
        ("upstream_request_id", data.get("request_id") or source.get("request_id") or request_id),
    ):
        text = safe_text(value, secret)
        if text:
            details[field] = text
    if http_status is not None:
        details["http_status"] = http_status
    generic = {"upstream video generation failed", "video generation failed", "generation failed", "provider request failed"}
    unspecified = not details.get("upstream_message") or details["upstream_message"].strip().rstrip(".").casefold() in generic
    details["reason_provided"] = not unspecified
    if http_status in (401, 403):
        suggestion = f"请在{'视频' if media == 'video' else '图片'}设置中测试当前 Key 的连接与模型权限。"
    elif http_status == 429:
        suggestion = "请核对上游限流或配额说明，稍后再处理。"
    elif http_status in (400, 422):
        suggestion = "请按上游错误码、原始原因和参数字段检查模型、分辨率、时长及参考素材。" if media == "video" else "请按上游原始原因和相关参数检查模型、尺寸、数量及参考图片。"
    elif unspecified:
        suggestion = "上游未提供具体失败原因。请将上游任务 ID、模型、提交时间和错误码提供给服务方，查询其后台日志；素材、内容审核、额度及服务异常均未获确认。"
    else:
        suggestion = "请按上游原始原因核对参数与素材；仍无法定位时，将任务 ID、错误码和提交时间提供给服务方。"
    details["suggestion"] = suggestion
    return details


def local_failure_details(stage, code, message, *, exception=None, secret=None, media="image"):
    details = {"stage": stage, "reason_provided": True, "local_message": safe_text(message, secret)}
    if exception is not None:
        details["exception_type"] = type(exception).__name__
        response = getattr(exception, "response", None)
        status = getattr(response, "status_code", None)
        if isinstance(response, dict):
            status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            service_code = safe_text(response.get("Error", {}).get("Code"), secret)
            if service_code:
                details["service_code"] = service_code
        if status is not None:
            details["http_status"] = status
    if "timeout" in code or "network" in code:
        suggestion = "请检查服务连接；超时不能确认上游是否完成，请先核对原任务。"
    elif stage == "download":
        suggestion = "请检查上游结果是否可下载、文件格式及大小；结果下载或校验失败不代表上游生成失败。"
    elif stage in ("storage", "reference_storage", "completion"):
        suggestion = "请检查存储服务、磁盘空间及数据库连接。"
    elif code in ("provider_auth", "video_auth"):
        suggestion = "请测试当前 Key 的连接与模型权限。"
    else:
        suggestion = "请结合失败阶段和错误码排查；联系维护人员时提供任务 ID。"
    if media == "video":
        suggestion += "保留原任务，恢复查询或重试保存，避免重复提交。"
    details["suggestion"] = suggestion
    return details

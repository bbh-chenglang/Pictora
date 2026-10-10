"""Keep useful upstream diagnostics without retaining keys or signed media URLs."""
import re


def safe_text(value, secret=None, limit=2000):
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return None
    text = str(value)
    if secret:
        text = text.replace(secret, "[redacted]")
    text = re.sub(r"https?://[^\s\"<>]+", "[素材链接已隐藏]", text, flags=re.I)
    text = re.sub(r"(?i)\bBearer\s+[^\s\",;]+", "Bearer [redacted]", text)
    text = re.sub(r"\bsk-[A-Za-z0-9_-]+", "[redacted]", text)
    return text[:limit].strip() or None


def failure_details(data, stage, *, secret=None, http_status=None, request_id=None):
    data = data if isinstance(data, dict) else {}
    error = data.get("error")
    source = error if isinstance(error, dict) else data
    message = source.get("message") or source.get("detail") or data.get("failure_reason")
    if isinstance(error, str):
        message = error
    details = {"stage": stage}
    for field, value in (
        ("upstream_code", source.get("code")),
        ("upstream_message", message),
        ("parameter", source.get("param") or source.get("parameter")),
        ("upstream_request_id", data.get("request_id") or source.get("request_id") or request_id),
    ):
        text = safe_text(value, secret)
        if text:
            details[field] = text
    if http_status is not None:
        details["http_status"] = http_status
    generic_messages = {"upstream video generation failed", "video generation failed", "generation failed"}
    unspecified = not details.get("upstream_message") or details["upstream_message"].strip().rstrip(".").casefold() in generic_messages
    details["reason_provided"] = not unspecified
    code = details.get("upstream_code", "").casefold()
    if http_status in (401, 403):
        suggestion = "请在视频设置中测试当前 Key 的连接与模型权限。"
    elif http_status == 429:
        suggestion = "请核对上游限流或配额说明，稍后再处理。"
    elif http_status in (400, 422):
        suggestion = "请按上游错误码、原始原因和参数字段检查模型、分辨率、时长及参考素材。"
    elif code == "upstream_generation_failed" or unspecified:
        suggestion = "上游未提供具体失败原因。请将上游任务 ID、模型、提交时间和错误码提供给服务方，查询其后台日志；素材、内容审核、额度及服务异常均未获确认。"
    else:
        suggestion = "请按上游原始原因核对参数与素材；仍无法定位时，将任务 ID、错误码和提交时间提供给服务方。"
    details["suggestion"] = suggestion
    return details


def failure_summary(details, status=None):
    stage = {"submission": "视频提交被上游拒绝", "query": "上游任务查询失败", "generation": "上游视频生成失败"}.get(details["stage"], "视频处理失败")
    parts = [stage]
    if status in ("cancelled", "expired"):
        parts[0] = "上游视频任务已取消" if status == "cancelled" else "上游视频任务已过期"
    if details.get("http_status"):
        parts.append("HTTP " + str(details["http_status"]))
    if details.get("upstream_code"):
        parts.append("错误码：" + details["upstream_code"])
    if details.get("reason_provided"):
        parts.append("上游原因：" + details["upstream_message"])
    else:
        parts.append("上游未提供具体原因，请展开失败详情查看排查信息")
    return "。".join(parts)

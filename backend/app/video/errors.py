"""Video error summaries using shared public diagnostics."""
from app.error_details import failure_details, safe_text


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

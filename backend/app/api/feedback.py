import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings
from app.dependencies import get_current_user
from app.schemas.auth import StoredSessionUser
from app.schemas.feedback import FeedbackRequest, FeedbackResponse


router = APIRouter(prefix="/api/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackResponse)
async def submit_feedback(
    request: FeedbackRequest,
    user: StoredSessionUser = Depends(get_current_user),
) -> FeedbackResponse:
    webhook_url = Settings().wecom_webhook_url.get_secret_value().strip()
    if not webhook_url:
        raise HTTPException(
            503,
            {"error": {"code": "feedback_not_configured", "message": "留言服务暂未配置"}},
        )

    content = "\n".join(
        [
            "GenImage 留言反馈",
            f"用户：{user.username}",
            f"联系方式：{request.contact or '未提供'}",
            f"留言：{request.message}",
        ]
    )
    payload = {"msgtype": "text", "text": {"content": content}}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(webhook_url, json=payload)
        response_data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            502,
            {"error": {"code": "feedback_delivery_failed", "message": "留言发送失败，请稍后重试"}},
        ) from exc

    if response.status_code >= 400 or response_data.get("errcode", 0) != 0:
        raise HTTPException(
            502,
            {"error": {"code": "feedback_delivery_failed", "message": "留言发送失败，请稍后重试"}},
        )
    return FeedbackResponse(message="留言已提交")

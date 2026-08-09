from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.dependencies import get_current_user
from app.main import app
from app.schemas.auth import StoredSessionUser


class FakeWebhookResponse:
    status_code = 200

    def json(self):
        return {"errcode": 0, "errmsg": "ok"}


class FakeWebhookClient:
    payload = None
    url = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def post(self, url, json):
        self.url = url
        self.payload = json
        return FakeWebhookResponse()


def test_feedback_sends_message_and_optional_contact_to_wecom(monkeypatch) -> None:
    fake_client = FakeWebhookClient()
    monkeypatch.setattr("app.api.feedback.Settings", lambda: SimpleNamespace(
        wecom_webhook_url=SimpleNamespace(get_secret_value=lambda: "https://wecom.example/webhook"),
    ))
    monkeypatch.setattr("app.api.feedback.httpx.AsyncClient", lambda timeout: fake_client)
    app.dependency_overrides[get_current_user] = lambda: StoredSessionUser(
        id=1, username="alice", api_key="", model="gpt-image-1.5"
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/feedback",
                json={"message": "希望增加更多图片尺寸", "contact": "alice@example.com"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake_client.url == "https://wecom.example/webhook"
    assert fake_client.payload == {
        "msgtype": "text",
        "text": {
            "content": "GenImage 留言反馈\n用户：alice\n联系方式：alice@example.com\n留言：希望增加更多图片尺寸",
        },
    }


def test_feedback_requires_message(monkeypatch) -> None:
    monkeypatch.setattr("app.api.feedback.Settings", lambda: SimpleNamespace(
        wecom_webhook_url=SimpleNamespace(get_secret_value=lambda: "https://wecom.example/webhook"),
    ))
    app.dependency_overrides[get_current_user] = lambda: StoredSessionUser(
        id=1, username="alice", api_key="", model="gpt-image-1.5"
    )
    try:
        with TestClient(app) as client:
            response = client.post("/api/feedback", json={"message": "   "})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422

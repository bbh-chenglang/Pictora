from email.message import EmailMessage

import pytest

from app.config import Settings
from app.services.email_sender import EmailSender, EmailSenderNotConfiguredError


def test_email_sender_uses_gmail_ssl_port_and_app_password(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    class FakeSmtp:
        def __init__(self, host, port, *, timeout, context) -> None:
            calls.update(host=host, port=port, timeout=timeout, context=context)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def login(self, username: str, password: str) -> None:
            calls.update(username=username, password=password)

        def send_message(self, message: EmailMessage) -> None:
            calls["recipient"] = message["To"]

    monkeypatch.setattr("app.services.email_sender.smtplib.SMTP_SSL", FakeSmtp)
    sender = EmailSender(Settings(
        smtp_host="smtp.gmail.com",
        smtp_port=465,
        smtp_username="sender@gmail.com",
        smtp_app_password="app-password",
        smtp_sender="sender@gmail.com",
    ))
    message = EmailMessage()
    message["To"] = "alice@example.com"

    sender._send(message, "sender@gmail.com", "app-password")

    assert calls["host"] == "smtp.gmail.com"
    assert calls["port"] == 465
    assert calls["username"] == "sender@gmail.com"
    assert calls["password"] == "app-password"
    assert calls["recipient"] == "alice@example.com"


@pytest.mark.asyncio
async def test_email_sender_requires_credentials() -> None:
    sender = EmailSender(Settings(smtp_username="", smtp_app_password="", smtp_sender=""))

    with pytest.raises(EmailSenderNotConfiguredError):
        await sender.send_verification_code("alice@example.com", "123456")

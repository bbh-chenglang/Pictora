import asyncio
import smtplib
import ssl
from email.message import EmailMessage

from app.config import Settings


class EmailSenderNotConfiguredError(Exception):
    pass


class EmailDeliveryError(Exception):
    pass


class EmailSender:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def send_verification_code(self, email: str, code: str) -> None:
        username = self.settings.smtp_username.strip()
        password = self.settings.smtp_app_password.get_secret_value().strip()
        sender = self.settings.smtp_sender.strip() or username
        if not username or not password or not sender:
            raise EmailSenderNotConfiguredError

        message = EmailMessage()
        message["Subject"] = "Pictora 注册验证码"
        message["From"] = sender
        message["To"] = email
        minutes = max(1, self.settings.verification_code_ttl_seconds // 60)
        message.set_content(
            f"你的 Pictora 注册验证码是：{code}\n\n"
            f"验证码将在 {minutes} 分钟后失效。若不是你本人操作，请忽略此邮件。"
        )

        try:
            await asyncio.to_thread(self._send, message, username, password)
        except (OSError, smtplib.SMTPException) as exc:
            raise EmailDeliveryError from exc

    def _send(self, message: EmailMessage, username: str, password: str) -> None:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(
            self.settings.smtp_host,
            self.settings.smtp_port,
            timeout=20,
            context=context,
        ) as smtp:
            smtp.login(username, password)
            smtp.send_message(message)

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    cookie_secure: bool = False
    openai_api_key: SecretStr = SecretStr("")
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-image-1"
    custom_api_key: SecretStr = SecretStr("")
    custom_provider_name: str = "北海AI"
    custom_base_url: str = "https://sub.beibeihai.xyz/v1"
    custom_model: str = "gpt-image-1.5"
    wecom_webhook_url: SecretStr = SecretStr("")
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465
    smtp_username: str = ""
    smtp_app_password: SecretStr = SecretStr("")
    smtp_sender: str = ""
    admin_emails: str = ""
    verification_code_ttl_seconds: int = 10 * 60
    verification_code_cooldown_seconds: int = 60

    @property
    def admin_email_set(self) -> set[str]:
        return {
            email.strip().lower()
            for email in self.admin_emails.split(",")
            if email.strip()
        }

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        extra="ignore",
    )

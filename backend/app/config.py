from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: SecretStr = SecretStr("")
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-image-1"
    custom_api_key: SecretStr = SecretStr("")
    custom_provider_name: str = "北海AI"
    custom_base_url: str = "https://sub.beibeihai.xyz/v1"
    custom_model: str = "gpt-image-1.5"

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        extra="ignore",
    )

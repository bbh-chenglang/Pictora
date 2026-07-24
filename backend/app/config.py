from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-image-1"
    custom_api_key: str = ""
    custom_base_url: str = "http://localhost:11434/v1"
    custom_model: str = "gpt-image-1"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

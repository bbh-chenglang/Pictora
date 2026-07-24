from collections.abc import Mapping
from typing import Any

from app.config import Settings
from app.providers.base import ImageProvider, ProviderNotFoundError
from app.providers.compatible_provider import CompatibleProvider
from app.providers.openai_provider import OpenAIProvider
from app.schemas.common import ProviderModel


def _secret_value(value: Any) -> str:
    return value.get_secret_value() if hasattr(value, "get_secret_value") else str(value or "")


class ProviderRegistry:
    def __init__(self, providers: Mapping[str, ImageProvider]) -> None:
        self._providers = dict(providers)

    @classmethod
    def from_settings(cls, settings: Settings) -> "ProviderRegistry":
        providers: dict[str, ImageProvider] = {}
        if _secret_value(settings.openai_api_key).strip():
            providers["openai"] = OpenAIProvider(
                settings.openai_api_key,
                settings.openai_base_url,
                settings.openai_model,
            )
        if _secret_value(settings.custom_api_key).strip():
            providers["compatible"] = CompatibleProvider(
                settings.custom_api_key,
                settings.custom_base_url,
                settings.custom_model,
            )
        return cls(providers)

    def resolve(self, provider_id: str) -> ImageProvider:
        try:
            return self._providers[provider_id]
        except KeyError:
            raise ProviderNotFoundError(provider_id) from None

    def list_models(self) -> list[ProviderModel]:
        return [
            ProviderModel(id=provider_id, label=provider.label, models=[provider.model])
            for provider_id, provider in self._providers.items()
        ]

from app.providers.openai_provider import OpenAIProvider


class CompatibleProvider(OpenAIProvider):
    provider_id = "compatible"
    label = "Compatible API"

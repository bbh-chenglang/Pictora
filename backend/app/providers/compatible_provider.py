from app.providers.openai_provider import OpenAIProvider


class CompatibleProvider(OpenAIProvider):
    provider_id = "compatible"
    label = "兼容接口"

    def __init__(self, api_key, base_url, model, provider_name: str = "兼容接口", client=None):
        super().__init__(api_key, base_url, model, client)
        self.label = provider_name.strip() or self.label

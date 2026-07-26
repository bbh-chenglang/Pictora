from app.providers.openai_provider import OpenAIProvider


COMPATIBLE_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/150.0.0.0 Safari/537.36"
)


class CompatibleProvider(OpenAIProvider):
    provider_id = "compatible"
    label = "兼容接口"

    def __init__(self, api_key, base_url, model, provider_name: str = "兼容接口", client=None):
        super().__init__(
            api_key,
            base_url,
            model,
            client,
            default_headers={"User-Agent": COMPATIBLE_USER_AGENT},
        )
        self.label = provider_name.strip() or self.label

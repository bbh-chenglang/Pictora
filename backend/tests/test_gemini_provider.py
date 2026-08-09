from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from app.providers.gemini_provider import GeminiProvider
from app.schemas.generate import GenerateRequest


class FakeCompletions:
    def __init__(self, response):
        self.response = response
        self.request = None

    async def create(self, **kwargs):
        self.request = kwargs
        return self.response


@pytest.mark.asyncio
async def test_gemini_provider_extracts_data_url_and_markdown_images():
    completions = FakeCompletions(
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=[
                            {"type": "text", "text": "generated"},
                            {"type": "image_url", "image_url": {"url": "data:image/png;base64,YWJj"}},
                            {"b64_json": "ZGVm"},
                            {"type": "text", "text": "![image](https://cdn.example/cat.png)"},
                        ]
                    )
                )
            ]
        )
    )
    provider = GeminiProvider(
        api_key=SecretStr("secret"),
        base_url="https://sub.beibeihai.xyz/v1",
        model="gemini-2.5-flash-image",
        client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
    )

    response = await provider.generate_image(
        GenerateRequest(provider="gemini", model="gemini-2.5-flash-image", prompt="生成两只小猫")
    )

    assert len(response.images) == 3
    assert response.images[0].base64_data == "data:image/png;base64,YWJj"
    assert response.images[1].base64_data == "data:image/png;base64,ZGVm"
    assert response.images[2].url == "https://cdn.example/cat.png"
    assert completions.request == {
        "model": "gemini-2.5-flash-image",
        "messages": [{"role": "user", "content": "生成两只小猫"}],
    }

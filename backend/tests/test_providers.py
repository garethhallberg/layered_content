from app.providers.anthropic import AnthropicProvider
from app.providers.base import Completion
from app.config import get_settings
from app.providers.mistral import MistralProvider
from app.providers.openai import OpenAIProvider


def test_provider_adapter_contract_without_api_keys(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("MISTRAL_API_KEY", "")
    get_settings.cache_clear()
    for provider in [OpenAIProvider(), AnthropicProvider(), MistralProvider()]:
        completion = provider.complete(
            [{"role": "user", "content": "Hello"}],
            model="test-model",
            max_tokens=50,
        )
        assert isinstance(completion, Completion)
        assert completion.content
        assert provider.count_tokens("one two three", model="test-model") >= 1

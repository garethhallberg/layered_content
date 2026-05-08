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


def test_openai_uses_max_completion_tokens(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()
    captured = {}

    class FakeResponse:
        is_error = False

        def json(self):
            return {
                "id": "chatcmpl_test",
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1},
            }

    def fake_post(url, *, headers, json, timeout):
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr("app.providers.openai.httpx.post", fake_post)

    completion = OpenAIProvider().complete(
        [{"role": "user", "content": "Hello"}],
        model="gpt-5-mini",
        max_tokens=123,
    )

    assert completion.content == "ok"
    assert captured["json"]["max_completion_tokens"] == 123
    assert "max_tokens" not in captured["json"]

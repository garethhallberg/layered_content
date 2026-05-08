from app.providers.anthropic import AnthropicProvider
from app.providers.base import LLMProvider
from app.providers.mistral import MistralProvider
from app.providers.openai import OpenAIProvider


def get_provider(name: str) -> LLMProvider:
    providers = {
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "mistral": MistralProvider,
    }
    try:
        return providers[name.lower()]()
    except KeyError as exc:
        raise ValueError(f"Unsupported LLM_PROVIDER {name!r}") from exc


from time import perf_counter

import httpx

from app.config import get_settings
from app.providers.base import Completion, Message, ProviderError, offline_completion, rough_count


class MistralProvider:
    name = "mistral"

    def count_tokens(self, text: str, *, model: str) -> int:
        return rough_count(text)

    def complete(
        self, messages: list[Message], *, model: str, max_tokens: int
    ) -> Completion:
        settings = get_settings()
        if not settings.mistral_api_key:
            return offline_completion(messages, model=model, max_tokens=max_tokens)

        started = perf_counter()
        response = httpx.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.mistral_api_key}"},
            json={"model": model, "messages": messages, "max_tokens": max_tokens},
            timeout=60,
        )
        if response.is_error:
            raise ProviderError(f"Mistral {response.status_code}: {response.text[:1000]}")
        payload = response.json()
        usage = payload.get("usage", {})
        return Completion(
            content=payload["choices"][0]["message"]["content"],
            prompt_tokens=usage.get("prompt_tokens", self.count_tokens(str(messages), model=model)),
            completion_tokens=usage.get("completion_tokens", 0),
            latency_ms=int((perf_counter() - started) * 1000),
            raw={"id": payload.get("id")},
        )

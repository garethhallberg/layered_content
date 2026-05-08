from time import perf_counter

import httpx

from app.config import get_settings
from app.providers.base import Completion, Message, ProviderError, offline_completion, rough_count


class AnthropicProvider:
    name = "anthropic"

    def count_tokens(self, text: str, *, model: str) -> int:
        return rough_count(text)

    def complete(
        self, messages: list[Message], *, model: str, max_tokens: int
    ) -> Completion:
        settings = get_settings()
        if not settings.anthropic_api_key:
            return offline_completion(messages, model=model, max_tokens=max_tokens)

        started = perf_counter()
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        chat_messages = [
            {"role": m["role"], "content": m["content"]}
            for m in messages
            if m["role"] in {"user", "assistant"}
        ]
        response = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": model,
                "system": system,
                "messages": chat_messages,
                "max_tokens": max_tokens,
            },
            timeout=60,
        )
        if response.is_error:
            raise ProviderError(f"Anthropic {response.status_code}: {response.text[:1000]}")
        payload = response.json()
        usage = payload.get("usage", {})
        content = "".join(block.get("text", "") for block in payload.get("content", []))
        return Completion(
            content=content,
            prompt_tokens=usage.get("input_tokens", self.count_tokens(str(messages), model=model)),
            completion_tokens=usage.get("output_tokens", 0),
            latency_ms=int((perf_counter() - started) * 1000),
            raw={"id": payload.get("id")},
        )

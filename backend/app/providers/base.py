from dataclasses import dataclass
from typing import Literal, Protocol, TypedDict
import json
import re


class Message(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass
class Completion:
    content: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    raw: dict | None = None


class ProviderError(RuntimeError):
    pass


def provider_error(provider_name: str, response: object) -> ProviderError:
    status_code = getattr(response, "status_code", "unknown")
    text = "Provider request failed"
    code = None
    try:
        payload = response.json()  # type: ignore[attr-defined]
        error = payload.get("error", payload)
        if isinstance(error, dict):
            text = str(error.get("message") or error.get("type") or text)
            code = error.get("code")
        else:
            text = str(error)
    except Exception:
        reason = getattr(response, "reason_phrase", "")
        if reason:
            text = str(reason)
    suffix = f" (code: {code})" if code else ""
    return ProviderError(f"{provider_name} {status_code}: {text}{suffix}")


class LLMProvider(Protocol):
    name: str

    def complete(
        self, messages: list[Message], *, model: str, max_tokens: int
    ) -> Completion:
        ...

    def count_tokens(self, text: str, *, model: str) -> int:
        ...


def rough_count(text: str) -> int:
    return max(1, len(re.findall(r"\w+|[^\w\s]", text)))


def offline_completion(
    messages: list[Message], *, model: str, max_tokens: int, latency_ms: int = 0
) -> Completion:
    joined = "\n".join(message["content"] for message in messages)
    prompt_tokens = rough_count(joined)
    lower = joined.lower()

    if "return only json" in lower or '"sub_questions"' in lower:
        content = json.dumps(
            {
                "intent": "Answer the user's current document-analysis question.",
                "sub_questions": ["Identify the relevant document facts", "Answer concisely"],
                "relevant_doc_sections": ["Most relevant uploaded document excerpts"],
            }
        )
    elif "compress the following exchange" in lower:
        excerpt = " ".join(joined.split())[:700]
        content = (
            "Earlier discussion established the following context: "
            f"{excerpt}. Preserve these specifics for future follow-up questions."
        )
    else:
        last_user = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"),
            joined[-1000:],
        )
        content = (
            "Demo response: no API key is configured, so this local provider echoed "
            "the assembled context instead of calling a hosted model.\n\n"
            f"Current prompt focus:\n{last_user[-1200:]}"
        )

    completion_tokens = rough_count(content)
    return Completion(
        content=content[: max_tokens * 8],
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
        raw={"offline": True, "model": model},
    )

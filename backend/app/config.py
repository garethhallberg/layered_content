from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/layered_context.db"
    llm_provider: str = "openai"
    llm_model: str | None = None
    planner_model: str | None = None
    max_tokens: int = 900
    max_upload_bytes: int = 10 * 1024 * 1024
    max_message_chars: int = 12000
    recent_turn_count: int = 6
    summary_threshold_pairs: int = 4
    summary_batch_pairs: int = 4
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    mistral_api_key: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


DEFAULT_MODELS = {
    "openai": "gpt-5-mini",
    "anthropic": "claude-sonnet-4-20250514",
    "mistral": "mistral-small-2603",
}

KNOWN_MODEL_PREFIXES = {
    "openai": (
        "gpt-",
        "o1",
        "o3",
        "o4",
    ),
    "anthropic": ("claude-",),
    "mistral": (
        "mistral-",
        "ministral-",
        "magistral-",
        "codestral-",
        "devstral-",
        "pixtral-",
        "open-mistral-",
        "open-mixtral-",
    ),
}


def default_model_for_provider(provider: str) -> str:
    return DEFAULT_MODELS.get(provider.lower(), DEFAULT_MODELS["openai"])


def resolve_model(provider: str, requested_model: str | None) -> str:
    if requested_model and is_model_compatible(provider, requested_model):
        return requested_model
    return default_model_for_provider(provider)


def is_model_compatible(provider: str, model: str | None) -> bool:
    if not model:
        return False
    provider = provider.lower()
    model = model.lower()
    provider_prefixes = KNOWN_MODEL_PREFIXES.get(provider, ())
    if any(model.startswith(prefix) for prefix in provider_prefixes):
        return True
    other_prefixes = [
        prefix
        for other_provider, prefixes in KNOWN_MODEL_PREFIXES.items()
        if other_provider != provider
        for prefix in prefixes
    ]
    if any(model.startswith(prefix) for prefix in other_prefixes):
        return False
    return False

"""List the model ids a provider account can use, via each provider's models endpoint."""
from typing import Any, List, Optional

from sms.providers.registry import get_provider


def _openai_client(api_key: str, base_url: Optional[str]) -> Any:
    import openai
    kwargs: dict = {"api_key": api_key, "timeout": 30}
    if base_url:
        kwargs["base_url"] = base_url
    return openai.OpenAI(**kwargs)


def _anthropic_client(api_key: str, base_url: Optional[str]) -> Any:
    import anthropic
    kwargs: dict = {"api_key": api_key, "timeout": 30}
    if base_url:
        kwargs["base_url"] = base_url
    return anthropic.Anthropic(**kwargs)


def list_models(provider_id: str, api_key: str, base_url: Optional[str] = None) -> List[str]:
    """Return the sorted, de-duplicated model ids the key can use. Raises KeyError for an
    unknown provider; provider/network errors propagate for the caller to report."""
    spec = get_provider(provider_id)
    url = base_url or spec.base_url
    if spec.transport == "anthropic":
        page = _anthropic_client(api_key, url).models.list(limit=100)
        items = page.data if hasattr(page, "data") else page
    else:
        items = _openai_client(api_key, url).models.list().data
    # Gemini's OpenAI-compatible /models returns ids like "models/gemini-3.8-flash"; the chat
    # endpoint wants the bare id, so drop that resource prefix wherever it appears.
    ids = {_strip_models_prefix(str(m.id)) for m in items if getattr(m, "id", None)}
    return sorted(ids)


def _strip_models_prefix(model_id: str) -> str:
    return model_id[len("models/"):] if model_id.startswith("models/") else model_id

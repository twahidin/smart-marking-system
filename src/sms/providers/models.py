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
    ids = {str(m.id) for m in items if getattr(m, "id", None)}
    return sorted(ids)

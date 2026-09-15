from typing import Any, Optional

import instructor

from sms.providers.registry import get_provider


def build_client(provider_id: str, api_key: str, base_url: Optional[str] = None) -> Any:
    """Return an instructor client for the provider. Raises KeyError for unknown providers."""
    spec = get_provider(provider_id)
    mode = getattr(instructor.Mode, spec.mode)
    url = base_url or spec.base_url
    if spec.transport == "anthropic":
        import anthropic
        kwargs = {"api_key": api_key}
        if url:
            kwargs["base_url"] = url
        return instructor.from_anthropic(anthropic.Anthropic(**kwargs), mode=mode)
    import openai
    kwargs = {"api_key": api_key}
    if url:
        kwargs["base_url"] = url
    return instructor.from_openai(openai.OpenAI(**kwargs), mode=mode)

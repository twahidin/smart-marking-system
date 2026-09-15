from dataclasses import asdict, dataclass
from typing import Optional, Tuple

DEFAULT_PROVIDER = "tokenrouter"


@dataclass(frozen=True)
class ModelSpec:
    id: str
    label: str
    vision: bool


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    label: str
    transport: str            # "openai_compatible" | "openai" | "anthropic"
    base_url: Optional[str]   # None = SDK default
    mode: str                 # instructor.Mode name
    default_model: str
    default_rpm: int
    models: Tuple[ModelSpec, ...]
    key_url: str
    note: str = ""
    base_url_editable: bool = False
    api_params: Optional[dict] = None   # extra kwargs every agent call needs (Anthropic: max_tokens)


PROVIDERS: Tuple[ProviderSpec, ...] = (
    ProviderSpec(
        id="tokenrouter", label="TokenRouter", transport="openai_compatible",
        base_url="https://api.tokenrouter.com/v1", mode="JSON",
        default_model="z-ai/glm-5.3-flash", default_rpm=60,
        models=(
            ModelSpec("z-ai/glm-5.3-flash", "GLM 5.3 Flash", True),
            ModelSpec("z-ai/glm-5.3-free", "GLM 5.3 (free — if your key allows it)", True),
        ),
        key_url="https://www.tokenrouter.com/",
        note="Use “Load models from provider” to see exactly what your key can use. Some keys "
             "include the free z-ai/glm-5.3-free model (8 requests a minute — set Requests per "
             "minute to 8 if you pick it).",
    ),
    ProviderSpec(
        id="openrouter", label="OpenRouter", transport="openai_compatible",
        base_url="https://openrouter.ai/api/v1", mode="JSON",
        default_model="z-ai/glm-5.3-flash", default_rpm=60,
        models=(
            ModelSpec("z-ai/glm-5.3-flash", "GLM 5.3 Flash", True),
            ModelSpec("anthropic/claude-sonnet-5", "Claude Sonnet 5", True),
            ModelSpec("openai/gpt-5-mini", "GPT-5 mini", True),
            ModelSpec("qwen/qwen3-vl-plus", "Qwen3 VL Plus", True),
            # Auto Router picks a model per request; it may choose a text-only model,
            # so it is marked text-only — pair it with a vision model for reading pages.
            ModelSpec("openrouter/auto", "Auto Router (picks a model per request)", False),
        ),
        key_url="https://openrouter.ai/keys",
        note="Auto Router (openrouter/auto) may pick a text-only model. If you use it, set a "
             "vision model under “Different model for reading pages”. OpenRouter's :free models "
             "cost nothing (≈50 requests/day until you've bought $10 of credits, then 1,000/day) — "
             "load models and look for the :free suffix.",
    ),
    ProviderSpec(
        id="openai", label="OpenAI", transport="openai", base_url=None, mode="TOOLS",
        default_model="gpt-5-mini", default_rpm=60,
        models=(
            ModelSpec("gpt-5-mini", "GPT-5 mini", True),
            ModelSpec("gpt-5.4-mini", "GPT-5.4 mini", True),
            ModelSpec("gpt-5.5", "GPT-5.5", True),
        ),
        key_url="https://platform.openai.com/api-keys",
    ),
    ProviderSpec(
        id="anthropic", label="Anthropic", transport="anthropic", base_url=None, mode="ANTHROPIC_TOOLS",
        default_model="claude-opus-5", default_rpm=60,
        models=(
            ModelSpec("claude-opus-5", "Claude Opus 5", True),
            ModelSpec("claude-sonnet-5", "Claude Sonnet 5", True),
            ModelSpec("claude-haiku-4-5", "Claude Haiku 4.5", True),
        ),
        key_url="https://console.anthropic.com/settings/keys",
        api_params={"max_tokens": 8192},
    ),
    ProviderSpec(
        id="moonshot", label="Moonshot (Kimi)", transport="openai_compatible",
        base_url="https://api.moonshot.ai/v1", mode="JSON",
        default_model="kimi-k2.6", default_rpm=60,
        models=(
            ModelSpec("kimi-k2.6", "Kimi K2.6", True),
            ModelSpec("kimi-k3", "Kimi K3", True),
        ),
        key_url="https://platform.moonshot.ai/",
    ),
    ProviderSpec(
        id="qwen", label="Qwen (Alibaba Model Studio)", transport="openai_compatible",
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1", mode="JSON",
        default_model="qwen3-vl-plus", default_rpm=60,
        models=(
            ModelSpec("qwen3-vl-plus", "Qwen3 VL Plus", True),
            ModelSpec("qvq-max", "QVQ Max", True),
            ModelSpec("qwen-plus", "Qwen Plus (text only)", False),
        ),
        key_url="https://modelstudio.console.alibabacloud.com/",
        note="Model Studio now issues workspace-specific URLs like "
             "https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1. "
             "If the default URL is rejected, paste yours here.",
        base_url_editable=True,
    ),
    ProviderSpec(
        id="google", label="Google Gemini", transport="openai_compatible",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/", mode="JSON",
        default_model="gemini-3.8-flash", default_rpm=10,
        models=(
            ModelSpec("gemini-3.8-flash", "Gemini 3.8 Flash", True),
            ModelSpec("gemini-3.1-flash-lite", "Gemini 3.1 Flash-Lite", True),
            ModelSpec("gemini-2.5-flash", "Gemini 2.5 Flash", True),
        ),
        key_url="https://aistudio.google.com/apikey",
        note="Free tier: no card needed; roughly 10–30 requests a minute and hundreds per day "
             "depending on the model — enough for a class. Limits change; the Test connection "
             "button tells you if a model is available on your key.",
    ),
)

_BY_ID = {p.id: p for p in PROVIDERS}


def get_provider(provider_id: str) -> ProviderSpec:
    try:
        return _BY_ID[provider_id]
    except KeyError:
        raise KeyError(f"Unknown provider: {provider_id!r}. Known: {sorted(_BY_ID)}") from None


def registry_as_dicts() -> list:
    dicts = [asdict(p) for p in PROVIDERS]
    for d in dicts:
        d["models"] = list(d["models"])
    return dicts

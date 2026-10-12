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
    custom_models: bool = False         # provider lets the user save their own model ids


PROVIDERS: Tuple[ProviderSpec, ...] = (
    ProviderSpec(
        id="tokenrouter", label="TokenRouter", transport="openai_compatible",
        base_url="https://api.tokenrouter.com/v1", mode="JSON",
        default_model="z-ai/glm-5.3-flash", default_rpm=60,
        # Cheapest first. Every preset passed the Settings connection test (text + reading an image)
        # through TokenRouter in Oct 2026; z-ai/glm-5.3-free is no longer offered.
        models=(
            ModelSpec("z-ai/glm-5.3-flash", "GLM 5.3 Flash", True),
            ModelSpec("anthropic/claude-haiku-5.5", "Claude Haiku 5.5", True),
            ModelSpec("openai/gpt-6-luna", "GPT-6 Luna", True),
            ModelSpec("qwen/qwen3.8-flash", "Qwen3.8 Flash", True),
            ModelSpec("google/gemini-3.8-flash", "Gemini 3.8 Flash", True),
            ModelSpec("anthropic/claude-sonnet-5.5", "Claude Sonnet 5.5", True),
            ModelSpec("openai/gpt-6.1-sol", "GPT-6.1 Sol", True),
            ModelSpec("anthropic/claude-opus-5.5", "Claude Opus 5.5", True),
        ),
        key_url="https://www.tokenrouter.com/",
        note="Models are listed cheapest first. Use “Load models from provider” to see everything "
             "your key can use.",
        custom_models=True,
    ),
    ProviderSpec(
        id="openrouter", label="OpenRouter", transport="openai_compatible",
        base_url="https://openrouter.ai/api/v1", mode="JSON",
        default_model="z-ai/glm-5.3-flash", default_rpm=60,
        # Cheapest first; every preset passed the Settings connection test (text + reading an image)
        # through OpenRouter in Oct 2026.
        models=(
            ModelSpec("z-ai/glm-5.3-flash", "GLM 5.3 Flash", True),
            ModelSpec("anthropic/claude-haiku-5.5", "Claude Haiku 5.5", True),
            ModelSpec("openai/gpt-6-luna", "GPT-6 Luna", True),
            ModelSpec("qwen/qwen3.8-flash", "Qwen3.8 Flash", True),
            ModelSpec("google/gemini-3.8-flash", "Gemini 3.8 Flash", True),
            ModelSpec("anthropic/claude-sonnet-5.5", "Claude Sonnet 5.5", True),
            ModelSpec("openai/gpt-6.1-sol", "GPT-6.1 Sol", True),
            ModelSpec("anthropic/claude-opus-5.5", "Claude Opus 5.5", True),
            # TypeSafe's router: picks a model and reasoning effort per request, so its price varies.
            # (TokenRouter's typesafe/jev-1.13 is a "decisions" model on another endpoint and cannot mark.)
            ModelSpec("typesafe/jev-router", "Jev Router (TypeSafe)", True),
            # Auto Router picks a model per request; it may choose a text-only model,
            # so it is marked text-only — pair it with a vision model for reading pages.
            ModelSpec("openrouter/auto", "Auto Router (picks a model per request)", False),
        ),
        key_url="https://openrouter.ai/keys",
        note="Auto Router (openrouter/auto) may pick a text-only model. If you use it, set a "
             "vision model under “Different model for reading pages”. OpenRouter's :free models "
             "cost nothing (≈50 requests/day until you've bought $10 of credits, then 1,000/day) — "
             "load models and look for the :free suffix.",
        custom_models=True,
    ),
    ProviderSpec(
        # Current lines, cheapest first. All accept a forced tool call and structured outputs; they reject
        # max_tokens, which no OpenAI call in the app sends (api_params stays None, the probe is uncapped).
        id="openai", label="OpenAI", transport="openai", base_url=None, mode="TOOLS",
        default_model="gpt-6-luna", default_rpm=60,
        models=(
            ModelSpec("gpt-6-luna", "GPT-6 Luna", True),
            ModelSpec("gpt-6.1-sol", "GPT-6.1 Sol", True),
            ModelSpec("gpt-6-astra", "GPT-6 Astra (most capable, priciest)", True),
        ),
        key_url="https://platform.openai.com/api-keys",
    ),
    ProviderSpec(
        # Reasoning-tools mode sends tool_choice "auto" plus a "return only the tool call" instruction:
        # Claude Opus 5.5, Sonnet 5.5 and Fable 5.1 reject a forced tool (ANTHROPIC_TOOLS) with a 400.
        id="anthropic", label="Anthropic", transport="anthropic", base_url=None, mode="ANTHROPIC_REASONING_TOOLS",
        default_model="claude-opus-5-5", default_rpm=60,
        models=(
            ModelSpec("claude-opus-5-5", "Claude Opus 5.5", True),
            ModelSpec("claude-sonnet-5-5", "Claude Sonnet 5.5", True),
            ModelSpec("claude-haiku-5-5", "Claude Haiku 5.5", True),
            ModelSpec("claude-fable-5-1", "Claude Fable 5.1 (most capable, priciest)", True),
        ),
        key_url="https://console.anthropic.com/settings/keys",
        # Thinking is always on for these models and counts toward max_tokens, so leave room beyond the answer.
        api_params={"max_tokens": 16000},
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


def providers_with_custom(custom: dict) -> list:
    """`registry_as_dicts()` with each provider's saved custom models appended to `models`."""
    dicts = registry_as_dicts()
    for d in dicts:
        d["models"] = d["models"] + custom.get(d["id"], [])
    return dicts

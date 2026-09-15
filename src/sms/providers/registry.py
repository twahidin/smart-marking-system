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
        default_model="z-ai/glm-5.3-free", default_rpm=8,
        models=(
            ModelSpec("z-ai/glm-5.3-free", "GLM 5.3 (free)", True),
            ModelSpec("z-ai/glm-5.3-flash", "GLM 5.3 Flash", True),
        ),
        key_url="https://www.tokenrouter.com/",
        note="Free tier: 8 requests a minute — about 30 s per script. When you create the key, "
             "lock Allowed Models to z-ai/glm-5.3-free so nothing routes to a paid model.",
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
        ),
        key_url="https://openrouter.ai/keys",
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

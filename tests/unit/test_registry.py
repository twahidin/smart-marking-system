import pytest

import instructor

from sms.providers.client import build_client
from sms.providers.registry import DEFAULT_PROVIDER, PROVIDERS, get_provider, registry_as_dicts


def test_default_provider_is_tokenrouter_free_glm():
    p = get_provider(DEFAULT_PROVIDER)
    assert p.id == "tokenrouter"
    assert p.default_model == "z-ai/glm-5.3-free"
    assert p.default_rpm == 8
    assert p.base_url == "https://api.tokenrouter.com/v1"


def test_all_six_providers_present_with_vision_default():
    ids = {p.id for p in PROVIDERS}
    assert ids == {"tokenrouter", "openrouter", "openai", "anthropic", "moonshot", "qwen"}
    for p in PROVIDERS:
        default = next(m for m in p.models if m.id == p.default_model)
        assert default.vision, f"{p.id} default model must support vision"


def test_unknown_provider_raises():
    with pytest.raises(KeyError):
        get_provider("nope")


def test_registry_as_dicts_is_json_shaped():
    d = registry_as_dicts()
    assert d[0]["id"] and isinstance(d[0]["models"], list) and "vision" in d[0]["models"][0]


@pytest.mark.parametrize("pid,mode", [
    ("tokenrouter", instructor.Mode.JSON),
    ("openrouter", instructor.Mode.JSON),
    ("moonshot", instructor.Mode.JSON),
    ("qwen", instructor.Mode.JSON),
    ("openai", instructor.Mode.TOOLS),
])
def test_build_client_openai_family(pid, mode):
    client = build_client(pid, api_key="sk-test")
    assert client.mode == mode
    spec = get_provider(pid)
    if spec.base_url:
        assert str(client.client.base_url).rstrip("/") == spec.base_url


def test_build_client_anthropic():
    client = build_client("anthropic", api_key="sk-ant-test")
    assert client.mode == instructor.Mode.ANTHROPIC_TOOLS


def test_anthropic_requires_max_tokens_param():
    assert get_provider("anthropic").api_params == {"max_tokens": 8192}
    assert get_provider("openai").api_params is None


def test_build_client_base_url_override():
    client = build_client("qwen", api_key="k", base_url="https://ws.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1")
    assert "maas.aliyuncs.com" in str(client.client.base_url)


def test_build_client_unknown_provider():
    with pytest.raises(KeyError):
        build_client("nope", api_key="k")

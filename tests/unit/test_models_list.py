import httpx
import pytest

from sms.providers.models import list_models


class FakeOpenAI:
    def __init__(self, ids):
        self._ids = ids
        outer = self

        class _Models:
            def list(self):
                class _Page:
                    data = [type("M", (), {"id": i})() for i in outer._ids]
                return _Page()

        self.models = _Models()


def test_lists_openai_compatible_models_sorted(monkeypatch):
    monkeypatch.setattr("sms.providers.models._openai_client", lambda api_key, base_url: FakeOpenAI(["z/b", "a/x", "a/x"]))
    assert list_models("tokenrouter", "k") == ["a/x", "z/b"]


def test_uses_provider_base_url_and_override(monkeypatch):
    seen = {}

    def factory(api_key, base_url):
        seen["url"] = base_url
        return FakeOpenAI([])

    monkeypatch.setattr("sms.providers.models._openai_client", factory)
    list_models("openrouter", "k")
    assert seen["url"] == "https://openrouter.ai/api/v1"
    list_models("qwen", "k", base_url="https://ws.example/compatible-mode/v1")
    assert seen["url"] == "https://ws.example/compatible-mode/v1"


def test_anthropic_uses_sdk_models_list(monkeypatch):
    class FakeAnthropic:
        class models:
            @staticmethod
            def list(limit=100):
                return [type("M", (), {"id": "claude-opus-5"})(), type("M", (), {"id": "claude-haiku-4-5"})()]

    monkeypatch.setattr("sms.providers.models._anthropic_client", lambda api_key, base_url: FakeAnthropic())
    assert list_models("anthropic", "k") == ["claude-haiku-4-5", "claude-opus-5"]


def test_unknown_provider_raises_keyerror():
    with pytest.raises(KeyError):
        list_models("nope", "k")


def test_provider_error_propagates(monkeypatch):
    class Boom:
        class models:
            @staticmethod
            def list():
                raise httpx.HTTPError("down")

    monkeypatch.setattr("sms.providers.models._openai_client", lambda api_key, base_url: Boom())
    with pytest.raises(httpx.HTTPError):
        list_models("openai", "k")

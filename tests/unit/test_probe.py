import instructor

from sms.providers.probe import PROBE_TIMEOUT_S, Digits, Pong, ProbeResult, probe, render_number_png


class FakeInstructor:
    """Mimics instructor client .chat.completions.create(response_model=...)."""

    def __init__(self, text_ok=True, vision_number=None, raise_text=None):
        self.text_ok = text_ok
        self.vision_number = vision_number
        self.raise_text = raise_text
        self.calls = []

        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.calls.append(kwargs)
                rm = kwargs["response_model"]
                if rm is Pong:
                    if outer.raise_text:
                        raise outer.raise_text
                    return Pong(ok=outer.text_ok)
                if rm is Digits:
                    return Digits(number=outer.vision_number)
                raise AssertionError(rm)

        class _Chat:
            completions = _Completions()

        self.chat = _Chat()


def test_render_png_is_png():
    assert render_number_png(42)[:8] == b"\x89PNG\r\n\x1a\n"


def test_probe_success(monkeypatch):
    fake = FakeInstructor(vision_number=None)

    def factory(provider, api_key, base_url=None):
        return fake

    monkeypatch.setattr("sms.providers.probe.random.randint", lambda a, b: 37)
    fake.vision_number = 37
    r = probe("tokenrouter", "z-ai/glm-5.3-free", "k", client_factory=factory)
    assert r.text.ok and r.vision.ok and r.text.error is None
    assert fake.calls[0]["model"] == "z-ai/glm-5.3-free"


def test_probe_vision_message_uses_instructor_image(monkeypatch):
    """instructor converts an Image per provider; a raw OpenAI-style dict is passed through and Anthropic 400s."""
    fake = FakeInstructor(vision_number=37)
    monkeypatch.setattr("sms.providers.probe.random.randint", lambda a, b: 37)
    probe("anthropic", "claude-sonnet-4-5", "k", client_factory=lambda *a, **k: fake)
    content = fake.calls[1]["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "What two-digit number is written in this image?"}
    assert isinstance(content[1], instructor.Image) and not isinstance(content[1], dict)
    assert content[1].media_type == "image/png"
    assert content[1].to_anthropic()["source"]["media_type"] == "image/png"


def test_probe_passes_timeout_to_both_calls():
    fake = FakeInstructor(vision_number=5)
    probe("openai", "gpt-5-mini", "k", client_factory=lambda *a, **k: fake)
    assert [c["timeout"] for c in fake.calls] == [PROBE_TIMEOUT_S, PROBE_TIMEOUT_S] and PROBE_TIMEOUT_S == 60


def test_probe_uses_extractor_model_for_vision(monkeypatch):
    fake = FakeInstructor(vision_number=5)
    monkeypatch.setattr("sms.providers.probe.random.randint", lambda a, b: 5)
    probe("openai", "gpt-5.5", "k", extractor_model="gpt-5-mini", client_factory=lambda *a, **k: fake)
    assert fake.calls[1]["model"] == "gpt-5-mini"


def test_probe_vision_mismatch_is_failure(monkeypatch):
    fake = FakeInstructor(vision_number=11)
    monkeypatch.setattr("sms.providers.probe.random.randint", lambda a, b: 22)
    r = probe("openai", "gpt-5-mini", "k", client_factory=lambda *a, **k: fake)
    assert r.text.ok and not r.vision.ok and "22" in r.vision.error


def test_probe_reports_provider_error():
    fake = FakeInstructor(raise_text=RuntimeError("invalid api key"))
    r = probe("openai", "gpt-5-mini", "k", client_factory=lambda *a, **k: fake)
    assert not r.text.ok and "invalid api key" in r.text.error
    assert isinstance(r.to_dict()["text"]["latency_ms"], int)

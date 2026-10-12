"""The Anthropic route against a fake server: what current Claude models accept, and a reply they actually give."""
import json

import anthropic
import httpx2
from pydantic import BaseModel

from sms.providers.client import build_client
from sms.providers.registry import get_provider


class Answer(BaseModel):
    number: int


def _client_with(monkeypatch, reply_content):
    sent = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append(json.loads(request.content))
        return httpx2.Response(200, json={
            "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
            "content": reply_content, "stop_reason": "tool_use", "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 5},
        })

    class Faked(anthropic.Anthropic):   # a subclass, so instructor's isinstance check still passes
        def __init__(self, **kw):
            super().__init__(**kw, http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler)))

    monkeypatch.setattr(anthropic, "Anthropic", Faked)
    return build_client("anthropic", "sk-ant-test"), sent


def test_never_forces_a_tool_and_parses_a_reply_that_thinks_first(monkeypatch):
    """Opus 5.5, Sonnet 5.5 and Fable 5.1 return 400 on tool_choice "tool"/"any", and always think before answering."""
    client, sent = _client_with(monkeypatch, [
        {"type": "thinking", "thinking": "", "signature": "sig"},
        {"type": "tool_use", "id": "toolu_1", "name": "Answer", "input": {"number": 42}},
    ])
    out = client.chat.completions.create(model="claude-opus-5-5", response_model=Answer, max_retries=0,
                                         messages=[{"role": "user", "content": "What is 6 x 7?"}],
                                         **get_provider("anthropic").api_params)
    assert out.number == 42
    body = sent[0]
    assert body["tool_choice"] == {"type": "auto"}
    assert [t["name"] for t in body["tools"]] == ["Answer"]
    assert "Return only the tool call" in json.dumps(body["system"])
    assert body["max_tokens"] == 16000 and "thinking" not in body

"""The OpenAI route against a fake server: current OpenAI models reject max_tokens, so marking must never send it."""
import json

import httpx
import openai
from pydantic import BaseModel

from sms.providers.client import build_client
from sms.providers.registry import get_provider


class Answer(BaseModel):
    number: int


def test_sends_a_forced_tool_call_and_no_max_tokens(monkeypatch):
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={
            "id": "chatcmpl-1", "object": "chat.completion", "created": 0, "model": "gpt-6-luna",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "Answer", "arguments": json.dumps({"number": 42})}}]}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        })

    class Faked(openai.OpenAI):   # a subclass, so instructor's isinstance check still passes
        def __init__(self, **kw):
            super().__init__(**kw, http_client=openai.DefaultHttpxClient(transport=httpx.MockTransport(handler)))

    monkeypatch.setattr(openai, "OpenAI", Faked)
    client = build_client("openai", "sk-test")
    out = client.chat.completions.create(model="gpt-6-luna", response_model=Answer, max_retries=0,
                                         messages=[{"role": "user", "content": "What is 6 x 7?"}],
                                         **(get_provider("openai").api_params or {}))
    assert out.number == 42
    body = sent[0]
    assert body["tool_choice"] == {"type": "function", "function": {"name": "Answer"}}
    assert "max_tokens" not in body and "max_completion_tokens" not in body

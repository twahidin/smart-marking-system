import os

import pytest

from sms.providers.probe import probe

pytestmark = pytest.mark.skipif(
    os.environ.get("SMS_LIVE_TESTS") != "1" or not os.environ.get("TOKENROUTER_API_KEY"),
    reason="set SMS_LIVE_TESTS=1 and TOKENROUTER_API_KEY to run",
)


def test_glm_free_text_and_vision():
    r = probe("tokenrouter", "z-ai/glm-5.3-free", os.environ["TOKENROUTER_API_KEY"])
    assert r.text.ok, r.text.error
    assert r.vision.ok, r.vision.error

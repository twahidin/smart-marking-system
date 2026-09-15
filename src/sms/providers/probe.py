import base64
import io
import random
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

import instructor
from pydantic import BaseModel, Field

from sms.providers.client import build_client
from sms.providers.errors import error_message

PROBE_TIMEOUT_S = 60


class Pong(BaseModel):
    ok: bool = Field(..., description="True if you can read this")


class Digits(BaseModel):
    number: int = Field(..., description="The number shown in the image")


@dataclass
class Check:
    ok: bool
    latency_ms: int
    error: Optional[str] = None


@dataclass
class ProbeResult:
    text: Check
    vision: Check

    def to_dict(self) -> dict:
        return {"text": self.text.__dict__, "vision": self.vision.__dict__}


def render_number_png(number: int) -> bytes:
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (160, 80), "white")
    draw = ImageDraw.Draw(img)
    text = str(number)
    # Default bitmap font is small; scale by drawing then resizing for legibility.
    small = Image.new("RGB", (40, 20), "white")
    ImageDraw.Draw(small).text((2, 4), text, fill="black")
    img.paste(small.resize((160, 80), Image.NEAREST))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _image_from_png(png_bytes: bytes) -> instructor.Image:
    b64 = base64.b64encode(png_bytes).decode()
    try:
        return instructor.Image.from_raw_base64(b64)
    except ValueError:  # pragma: no cover - defensive; PNG magic bytes are always recognised
        return instructor.Image(source=f"data:image/png;base64,{b64}", media_type="image/png", data=b64)


def _timed(fn: Callable[[], Any]) -> Check:
    t0 = time.monotonic()
    try:
        fn()
        return Check(ok=True, latency_ms=int((time.monotonic() - t0) * 1000))
    except AssertionError as e:
        return Check(ok=False, latency_ms=int((time.monotonic() - t0) * 1000), error=str(e))
    except Exception as e:  # noqa: BLE001 - we report every provider error to the teacher
        return Check(ok=False, latency_ms=int((time.monotonic() - t0) * 1000), error=error_message(e))


def probe(provider: str, model: str, api_key: str, extractor_model: Optional[str] = None,
          base_url: Optional[str] = None, client_factory: Callable[..., Any] = build_client) -> ProbeResult:
    client = client_factory(provider, api_key, base_url=base_url)

    def text_check() -> None:
        out = client.chat.completions.create(
            model=model,
            response_model=Pong,
            messages=[{"role": "user", "content": "Reply with ok=true."}],
            max_retries=0,
            max_tokens=256,
            timeout=PROBE_TIMEOUT_S,
        )
        assert out.ok, "Model replied but did not return ok=true"

    number = random.randint(10, 99)
    image = _image_from_png(render_number_png(number))

    def vision_check() -> None:
        # An instructor.Image is converted per provider (OpenAI image_url vs Anthropic
        # base64 source block); a raw OpenAI-style dict would be passed through untouched.
        out = client.chat.completions.create(
            model=extractor_model or model,
            response_model=Digits,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "What two-digit number is written in this image?"},
                    image,
                ],
            }],
            max_retries=0,
            max_tokens=256,
            timeout=PROBE_TIMEOUT_S,
        )
        assert out.number == number, f"Model read {out.number}, expected {number} — it may not support images"

    text = _timed(text_check)
    vision = _timed(vision_check) if text.ok else Check(ok=False, latency_ms=0, error="Skipped — text check failed")
    return ProbeResult(text=text, vision=vision)

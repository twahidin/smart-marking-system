import pytest

from sms.pipeline.router import SubjectRouter


def test_router_resolves_known_subjects():
    router = SubjectRouter()
    assert router.resolve("math") == "math"
    assert router.resolve(" Math ") == "math"


def test_router_rejects_unknown_subject():
    router = SubjectRouter()
    with pytest.raises(KeyError):
        router.resolve("fiction")


def test_router_returns_math_prompt_config():
    router = SubjectRouter()
    cfg = router.marker_prompt_config("math")
    assert cfg["background"]
    assert cfg["steps"]
    assert cfg["output_instructions"]
    assert cfg["reviewer_background"]


def test_router_language_and_science_have_prompt_data():
    router = SubjectRouter()
    for subject in ("language", "science"):
        cfg = router.marker_prompt_config(subject)
        assert cfg["background"] and cfg["steps"] and cfg["output_instructions"]


def test_router_knows_mt_and_computing():
    router = SubjectRouter()
    assert router.resolve("mt") == "mt" and router.resolve("computing") == "computing"
    for subject in ("mt", "computing"):
        cfg = router.marker_prompt_config(subject)
        assert cfg["background"] and cfg["reviewer_steps"]

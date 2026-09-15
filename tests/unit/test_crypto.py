from sms.providers.crypto import KeyCipher


def test_roundtrip_and_distinct_ciphertext():
    c = KeyCipher("a-secret-that-is-not-32-bytes")
    enc = c.encrypt("sk-abc")
    assert enc != "sk-abc"
    assert c.decrypt(enc) == "sk-abc"


def test_different_secret_cannot_decrypt():
    import pytest
    enc = KeyCipher("one").encrypt("sk-abc")
    with pytest.raises(ValueError):
        KeyCipher("two").decrypt(enc)

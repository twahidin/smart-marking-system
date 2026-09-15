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


def test_malformed_tokens_raise_value_error():
    import pytest
    c = KeyCipher("a-secret")
    with pytest.raises(ValueError):
        c.decrypt("héllo")
    with pytest.raises(ValueError):
        c.decrypt("not-a-token")

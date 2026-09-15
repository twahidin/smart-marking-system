import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


class KeyCipher:
    """Fernet cipher whose key is derived from SECRET_KEY (any length)."""

    def __init__(self, secret_key: str):
        digest = hashlib.sha256(secret_key.encode("utf-8")).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(digest))

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str) -> str:
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except InvalidToken as e:
            raise ValueError("Stored API key cannot be decrypted with this SECRET_KEY") from e

"""Symmetric encryption for subscription access-key private material.

Wraps Fernet (AES-128-CBC + HMAC-SHA256) with a single key loaded from
``SUBSCRIPTION_KEYSTORE_KEY``. The keystore stores ciphertext only; access-key
private bytes never live on disk in plaintext.
"""

from cryptography.fernet import Fernet


class Keystore:
    """Encrypt and decrypt access-key private bytes with a Fernet key."""

    def __init__(self, fernet_key: str) -> None:
        """Build a keystore from a base64 Fernet key.

        Args:
            fernet_key: Base64-encoded 32-byte key.

        Raises:
            ValueError: If the key is not a valid Fernet key.
        """
        self._fernet = Fernet(fernet_key.encode())

    def encrypt(self, plaintext: bytes) -> bytes:
        """Encrypt access-key private bytes."""
        return self._fernet.encrypt(plaintext)

    def decrypt(self, ciphertext: bytes) -> bytes:
        """Decrypt access-key private bytes.

        Raises:
            cryptography.fernet.InvalidToken: If ciphertext is not a valid
                Fernet token under the configured key.
        """
        return self._fernet.decrypt(ciphertext)

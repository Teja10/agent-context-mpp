"""Unit tests for the Fernet-backed Keystore."""

import pytest
from cryptography.fernet import Fernet, InvalidToken

from app.keystore import Keystore


def test_round_trip_recovers_plaintext() -> None:
    keystore = Keystore(Fernet.generate_key().decode())

    ciphertext = keystore.encrypt(b"hello world")

    assert keystore.decrypt(ciphertext) == b"hello world"


def test_ciphertext_is_non_deterministic() -> None:
    keystore = Keystore(Fernet.generate_key().decode())

    first = keystore.encrypt(b"same")
    second = keystore.encrypt(b"same")

    assert first != second


def test_decrypt_with_wrong_key_raises() -> None:
    a = Keystore(Fernet.generate_key().decode())
    b = Keystore(Fernet.generate_key().decode())

    ciphertext = a.encrypt(b"secret")

    with pytest.raises(InvalidToken):
        b.decrypt(ciphertext)


def test_invalid_key_raises_value_error() -> None:
    with pytest.raises(ValueError):
        Keystore("not-a-valid-fernet-key")

"""Wallet principal authentication via EIP-191 signature proof."""

from dataclasses import dataclass
from typing import Annotated

from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi import Depends, HTTPException, Request
from mpp import Challenge

from app.db.queries import upsert_wallet_principal
from app.state import AppState, get_state


@dataclass(frozen=True)
class WalletPrincipal:
    """Authenticated wallet identity extracted from a WalletProof header."""

    wallet_address: str


def parse_wallet_address(source: str) -> str:
    """Extract and lowercase-canonicalize a wallet address from a tempo source.

    Args:
        source: Credential source string (e.g. ``tempo:0xabc...``).

    Returns:
        Lowercase wallet address.

    Raises:
        ValueError: If source does not start with ``tempo:``.
    """
    prefix = "tempo:"
    if not source.startswith(prefix):
        raise ValueError(f"Credential source must start with '{prefix}'")
    address = source[len(prefix) :]
    if address == "":
        raise ValueError("Credential source must include a wallet address")
    return address.lower()


def _verify_wallet_proof(
    nonce: str, signature: str, realm: str, secret_key: str
) -> str:
    """Validate an HMAC-bound nonce and recover the signer address.

    Args:
        nonce: The challenge id issued by POST /auth/challenge.
        signature: Hex-encoded EIP-191 signature (with or without 0x prefix).
        realm: Server realm used for HMAC verification.
        secret_key: Server secret used for HMAC verification.

    Returns:
        Lowercase wallet address of the signer.

    Raises:
        ValueError: If the nonce HMAC is invalid or signature recovery fails.
    """
    challenge = Challenge(
        id=nonce,
        method="tempo",
        intent="auth",
        request={},
        realm=realm,
    )
    if not challenge.verify(secret_key, realm):
        raise ValueError("Invalid challenge nonce")
    message = encode_defunct(text=nonce)
    raw_sig = signature.removeprefix("0x")
    address: str = Account.recover_message(message, signature=bytes.fromhex(raw_sig))
    return address.lower()


def require_wallet_principal(
    request: Request,
    state: Annotated[AppState, Depends(get_state)],
) -> WalletPrincipal:
    """FastAPI dependency that authenticates via WalletProof header.

    Expects ``Authorization: WalletProof <nonce>.<hex_signature>``.

    Args:
        request: The incoming HTTP request.
        state: Application state containing MPP config and database engine.

    Returns:
        Authenticated WalletPrincipal.

    Raises:
        HTTPException: 401 if authentication fails for any reason.
    """
    authorization = request.headers.get("Authorization")
    if authorization is None:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0] != "WalletProof":
        raise HTTPException(status_code=401, detail="Invalid authorization scheme")
    payload_parts = parts[1].split(".", 1)
    if len(payload_parts) != 2:
        raise HTTPException(status_code=401, detail="Invalid WalletProof payload")
    nonce, signature = payload_parts
    try:
        wallet_address = _verify_wallet_proof(
            nonce, signature, state.mpp.realm, state.mpp.secret_key
        )
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid wallet proof")
    upsert_wallet_principal(state.engine, wallet_address)
    return WalletPrincipal(wallet_address=wallet_address)

"""Tempo AccountKeychain protocol and pure helpers for held-AK subscriptions.

Pattern B: subscriber root-signs an ``AccountKeychain.authorize_key`` tx that
delegates a server-held access key with a periodic ``TokenLimit`` and a
``CallScope.transfer_with_memo`` recipient pin. Thoth then charges
``transferWithMemo`` against the access key, signed via
``TempoTransaction.sign_access_key``.

The :class:`Keychain` protocol is the seam tests use to swap in a fake; the
production implementation lives in :mod:`app.tempo_keychain_live`.
"""
# pyright: reportMissingTypeStubs=false, reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Protocol
from uuid import UUID

from pytempo import (
    Call,
    CallScope,
    KeyRestrictions,
    SignatureType,
    TokenLimit,
)
from pytempo.contracts import AccountKeychain

PATHUSD_DECIMALS = 6
SUBSCRIPTION_MEMO_NAMESPACE = "sub"


class KeychainVerificationError(RuntimeError):
    """Raised when the on-chain authorize_key tx does not match expectations."""


class PeriodChargeError(RuntimeError):
    """Raised when the period transferWithMemo does not land successfully."""


@dataclass(frozen=True)
class PeriodCharge:
    """Verified period transferWithMemo receipt."""

    payment_reference: str
    block_number: int
    payer_address: str


def to_base_units(amount: Decimal) -> int:
    """Convert a PATHUSD decimal amount to integer base units."""
    return int(amount * (Decimal(10) ** PATHUSD_DECIMALS))


def derive_subscription_memo(
    publisher_id: UUID, wallet_address: str, period_start: datetime
) -> bytes:
    """Derive the 32-byte memo binding a subscription period to its parties."""
    payload = (
        f"{SUBSCRIPTION_MEMO_NAMESPACE}|{publisher_id}|"
        f"{wallet_address.lower()}|{int(period_start.timestamp())}"
    ).encode()
    return sha256(payload).digest()


def build_authorize_key_call(
    *,
    key_id: str,
    currency: str,
    monthly_price: Decimal,
    period_seconds: int,
    recipient: str,
    expiry: datetime,
) -> Call:
    """Build the AccountKeychain.authorize_key Call the subscriber must submit."""
    return AccountKeychain.authorize_key(
        key_id=key_id,
        signature_type=SignatureType.SECP256K1,
        restrictions=KeyRestrictions(
            expiry=int(expiry.timestamp()),
            limits=(
                TokenLimit(
                    token=currency,
                    limit=to_base_units(monthly_price),
                    period=period_seconds,
                ),
            ),
            allowed_calls=(
                CallScope.transfer_with_memo(target=currency, recipients=[recipient]),
            ),
        ),
    )


def build_revoke_key_call(*, key_id: str) -> Call:
    """Build the AccountKeychain.revoke_key Call surfaced in cancel responses."""
    return AccountKeychain.revoke_key(key_id=key_id)


def receipt_payload(
    *, tx_hash: str, block_number: int, network: str, charged_at: datetime
) -> dict[str, str]:
    """Shape a JSONB receipt payload matching the existing OneTimePurchase format."""
    if charged_at.tzinfo is None:
        charged_at = charged_at.replace(tzinfo=UTC)
    return {
        "status": "success",
        "timestamp": charged_at.isoformat(),
        "reference": tx_hash,
        "method": "tempo-access-key",
        "block_number": str(block_number),
        "network": network,
    }


class Keychain(Protocol):
    """Verify on-chain authorizations and submit access-key charges."""

    async def verify_authorize_key_tx(
        self,
        *,
        wallet_address: str,
        key_id: str,
        expected_monthly_price: Decimal,
        currency: str,
        expected_expiry: datetime,
        tx_hash: str,
    ) -> None:
        """Verify a subscriber's authorize_key tx matches the expected mandate."""
        ...

    async def submit_period_charge(
        self,
        *,
        access_key_private_key: str,
        wallet_address: str,
        recipient: str,
        currency: str,
        monthly_price: Decimal,
        memo: bytes,
    ) -> PeriodCharge:
        """Sign and broadcast one transferWithMemo against the access key."""
        ...

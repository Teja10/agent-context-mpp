"""Tempo AccountKeychain integration for held-AK subscription charges.

Pattern B: subscriber root-signs an ``AccountKeychain.authorize_key`` tx that
delegates a server-held access key with a periodic ``TokenLimit`` and a
``CallScope.transfer_with_memo`` recipient pin. Thoth then charges
``transferWithMemo`` against the access key, signed via
``TempoTransaction.sign_access_key``. Verification of each charge reuses the
same on-chain Transfer-log shape that ``mpp.methods.tempo.ChargeIntent``
already validates.

The :class:`Keychain` protocol is the seam tests use to swap in a fake. The
:class:`LiveKeychain` implementation talks to a Tempo RPC via web3.
"""
# pyright: reportMissingTypeStubs=false, reportMissingImports=false, reportMissingTypeArgument=false, reportArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Protocol
from uuid import UUID

from pytempo import (
    ACCOUNT_KEYCHAIN_ADDRESS,
    Call,
    CallScope,
    KeyRestrictions,
    SignatureType,
    TempoTransaction,
    TokenLimit,
)
from pytempo.contracts import TIP20, AccountKeychain
from web3 import Web3

# transferWithMemo(address,uint256,bytes32) event topic (TIP-20 extension).
TRANSFER_WITH_MEMO_TOPIC = (
    "0x57bc7354aa85aed339e000bccffabbc529466af35f0772c8f8ee1145927de7f0"
)
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


class LiveKeychain:
    """Production keychain that talks to a Tempo RPC via web3."""

    def __init__(self, *, rpc_url: str, chain_id: int) -> None:
        """Configure the keychain against a Tempo RPC."""
        self._rpc_url = rpc_url
        self._chain_id = chain_id

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
        """Verify a subscriber's authorize_key tx via on-chain getters."""
        w3 = Web3(Web3.HTTPProvider(self._rpc_url))
        receipt = w3.eth.get_transaction_receipt(_hex_to_hash(tx_hash))
        if receipt["status"] != 1:
            raise KeychainVerificationError(f"authorize_key tx {tx_hash} reverted")
        if str(receipt["from"]).lower() != wallet_address.lower():
            raise KeychainVerificationError(
                "authorize_key tx sender does not match authenticated wallet"
            )
        if str(receipt["to"]).lower() != ACCOUNT_KEYCHAIN_ADDRESS.lower():
            raise KeychainVerificationError(
                "authorize_key tx must target the AccountKeychain precompile"
            )
        info = AccountKeychain.get_key(
            w3, account_address=wallet_address, key_id=key_id
        )
        if info["is_revoked"]:
            raise KeychainVerificationError("access key is revoked on chain")
        expected_expiry_unix = int(expected_expiry.timestamp())
        if int(info["expiry"]) != expected_expiry_unix:
            raise KeychainVerificationError(
                f"access key expiry mismatch: chain={info['expiry']} "
                f"expected={expected_expiry_unix}"
            )
        if not info["enforce_limits"]:
            raise KeychainVerificationError("access key must enforce token limits")
        remaining = AccountKeychain.get_remaining_limit(
            w3,
            account_address=wallet_address,
            key_id=key_id,
            token_address=currency,
        )
        expected_units = to_base_units(expected_monthly_price)
        if int(remaining) != expected_units:
            raise KeychainVerificationError(
                f"access key spending limit mismatch: chain={remaining} "
                f"expected={expected_units}"
            )

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
        if len(memo) != 32:
            raise PeriodChargeError(f"memo must be 32 bytes, got {len(memo)}")
        w3 = Web3(Web3.HTTPProvider(self._rpc_url))
        base_amount = to_base_units(monthly_price)
        transfer_call = TIP20(currency).transfer_with_memo(
            to=recipient, amount=base_amount, memo=memo
        )
        nonce = w3.eth.get_transaction_count(w3.to_checksum_address(wallet_address))
        gas_price = w3.eth.gas_price
        tx = TempoTransaction.create(
            chain_id=self._chain_id,
            nonce=nonce,
            gas_limit=200_000,
            max_fee_per_gas=gas_price,
            max_priority_fee_per_gas=gas_price,
            calls=(transfer_call,),
        )
        signed = tx.sign_access_key(access_key_private_key, wallet_address)
        tx_hash = w3.eth.send_raw_transaction(signed.encode())
        tx_hash_hex = tx_hash.hex() if hasattr(tx_hash, "hex") else str(tx_hash)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
        if receipt["status"] != 1:
            raise PeriodChargeError(f"transferWithMemo {tx_hash_hex} reverted")
        if not _has_matching_transfer_log(
            receipt, currency, recipient, base_amount, memo
        ):
            raise PeriodChargeError(
                f"transferWithMemo {tx_hash_hex} missing matching log "
                f"(recipient={recipient}, amount={base_amount}, "
                f"memo=0x{memo.hex()})"
            )
        return PeriodCharge(
            payment_reference=tx_hash_hex,
            block_number=int(receipt["blockNumber"]),
            payer_address=wallet_address.lower(),
        )


def _has_matching_transfer_log(
    receipt: dict,
    currency: str,
    recipient: str,
    base_amount: int,
    memo: bytes,
) -> bool:
    """Return True when the receipt logs a TransferWithMemo matching the charge."""
    expected_memo_hex = "0x" + memo.hex()
    for log in receipt.get("logs", []):
        if str(log["address"]).lower() != currency.lower():
            continue
        topics = log["topics"]
        if len(topics) < 4:
            continue
        if topics[0].hex().lower() != TRANSFER_WITH_MEMO_TOPIC.lower():
            continue
        log_to = "0x" + topics[2].hex()[-40:]
        if log_to.lower() != recipient.lower():
            continue
        log_amount = int(log["data"][2:66], 16)
        if log_amount != base_amount:
            continue
        log_memo = "0x" + topics[3].hex()
        if log_memo.lower() == expected_memo_hex.lower():
            return True
    return False


def _hex_to_hash(value: str) -> bytes:
    """Convert a 0x-prefixed hex string to raw bytes for web3 RPC calls."""
    return bytes.fromhex(value.removeprefix("0x"))

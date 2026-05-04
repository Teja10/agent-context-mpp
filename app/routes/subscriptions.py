"""Per-publisher subscription endpoints (Pattern B: server-held access keys).

Signup:

1. ``POST /api/subscriptions/{handle}`` — server generates a fresh access
   keypair, returns the mandate parameters and period-1 charge metadata.
   Server stashes the access-key private bytes in an in-memory TTL cache
   keyed by ``session_token``.
2. Client root-signs and broadcasts ``AccountKeychain.authorize_key`` with
   the returned ``KeyRestrictions``.
3. ``POST /api/subscriptions/{handle}/activate`` — server verifies the
   ``authorize_key`` tx via on-chain getters, encrypts and persists the
   access-key private bytes, then immediately AK-signs and submits the
   period-1 ``transferWithMemo``. On success persists both the
   authorization and the period row atomically.

Cancel returns calldata for ``revoke_key`` so the client can render an
on-chain CTA. Renewal is handled by ``scripts/renew_subscriptions.py``.
"""
# pyright: reportMissingTypeStubs=false, reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated

from eth_account import Account
from eth_utils.address import to_checksum_address
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from pytempo import ACCOUNT_KEYCHAIN_ADDRESS

from app.auth import WalletPrincipal, require_wallet_principal
from app.db.queries import (
    get_active_authorization,
    get_active_subscription,
    get_publisher_by_handle,
    insert_authorization_with_key,
    insert_subscription_period,
    mark_authorization_status,
)
from app.db.records import (
    SubscriptionAuthorization,
    SubscriptionPeriod,
)
from app.state import AppState, PendingActivation, get_state
from app.tempo_keychain import (
    KeychainVerificationError,
    PeriodChargeError,
    build_authorize_key_call,
    build_revoke_key_call,
    derive_subscription_memo,
    receipt_payload,
    to_base_units,
)
from uuid import uuid4

router = APIRouter()

PERIOD_SECONDS_30_DAYS = 30 * 24 * 60 * 60
MAX_AUTHORIZATION_TERM_SECONDS = 365 * 24 * 60 * 60
ACTIVATION_TTL_SECONDS = 5 * 60


class CallPayload(BaseModel):
    """A pre-built calldata bundle the client submits as a Tempo Call."""

    model_config = ConfigDict(extra="forbid")

    to: str
    data: str


class MandateResponse(BaseModel):
    """Mandate parameters and period-1 charge details for a new subscription."""

    model_config = ConfigDict(extra="forbid")

    publisher_id: str
    key_id: str
    signature_type: str
    recipient: str
    currency: str
    monthly_price: str
    period_seconds: int
    expiry: datetime
    session_token: str
    authorize_call: CallPayload


class ActivateRequest(BaseModel):
    """Activate a subscription with the on-chain authorize_key tx hash."""

    model_config = ConfigDict(extra="forbid")

    session_token: str
    authorize_tx_hash: str


class SubscriptionPeriodResponse(BaseModel):
    """A persisted subscription period row, exposed to clients."""

    model_config = ConfigDict(extra="forbid")

    period_start: datetime
    period_end: datetime
    payment_reference: str
    receipt: dict[str, str]


class SubscriptionResponse(BaseModel):
    """Full subscription state returned by activate / GET / DELETE."""

    model_config = ConfigDict(extra="forbid")

    publisher_handle: str
    key_id: str
    status: str
    expiry: datetime
    current_period: SubscriptionPeriodResponse | None
    revoke_call: CallPayload | None


@router.post("/api/subscriptions/{handle}", status_code=200)
def begin_subscription(
    handle: str,
    state: Annotated[AppState, Depends(get_state)],
    principal: Annotated[WalletPrincipal, Depends(require_wallet_principal)],
) -> MandateResponse:
    """Generate a fresh access key and return the mandate parameters."""
    publisher = get_publisher_by_handle(state.engine, handle)
    if publisher is None:
        raise HTTPException(status_code=404, detail="Publisher not found")
    if publisher.status != "active":
        raise HTTPException(status_code=403, detail="Publisher is disabled")
    existing = get_active_authorization(
        state.engine, principal.wallet_address, publisher.id
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="Wallet already has an active subscription for this publisher",
        )
    monthly_price = publisher.default_subscription_price
    now = datetime.now(UTC)
    expiry = now + timedelta(seconds=MAX_AUTHORIZATION_TERM_SECONDS)
    access_key = Account.create()
    key_id = to_checksum_address(access_key.address).lower()
    session_token = secrets.token_urlsafe(32)
    state.activation_cache.put(
        session_token,
        PendingActivation(
            wallet_address=principal.wallet_address,
            publisher_id=publisher.id,
            key_id=key_id,
            access_key_private_key=access_key.key.hex(),
            monthly_price_str=str(monthly_price),
            expiry=expiry,
            period_seconds=PERIOD_SECONDS_30_DAYS,
            recipient=publisher.recipient_address,
            currency=state.pathusd_address,
            expires_at=now + timedelta(seconds=ACTIVATION_TTL_SECONDS),
        ),
    )
    authorize_call = build_authorize_key_call(
        key_id=key_id,
        currency=state.pathusd_address,
        monthly_price=monthly_price,
        period_seconds=PERIOD_SECONDS_30_DAYS,
        recipient=publisher.recipient_address,
        expiry=expiry,
    )
    return MandateResponse(
        publisher_id=str(publisher.id),
        key_id=key_id,
        signature_type="secp256k1",
        recipient=publisher.recipient_address,
        currency=state.pathusd_address,
        monthly_price=str(monthly_price),
        period_seconds=PERIOD_SECONDS_30_DAYS,
        expiry=expiry,
        session_token=session_token,
        authorize_call=_call_payload(ACCOUNT_KEYCHAIN_ADDRESS, authorize_call.data),
    )


@router.post("/api/subscriptions/{handle}/activate", status_code=201)
async def activate_subscription(
    handle: str,
    body: ActivateRequest,
    state: Annotated[AppState, Depends(get_state)],
    principal: Annotated[WalletPrincipal, Depends(require_wallet_principal)],
) -> SubscriptionResponse:
    """Verify the authorize_key tx and execute the period-1 charge."""
    publisher = get_publisher_by_handle(state.engine, handle)
    if publisher is None:
        raise HTTPException(status_code=404, detail="Publisher not found")
    pending = state.activation_cache.consume(body.session_token)
    if pending is None:
        raise HTTPException(status_code=400, detail="Session token expired or invalid")
    if pending.wallet_address != principal.wallet_address:
        raise HTTPException(
            status_code=400, detail="Session token does not match wallet"
        )
    if pending.publisher_id != publisher.id:
        raise HTTPException(
            status_code=400, detail="Session token does not match publisher"
        )
    monthly_price = Decimal(pending.monthly_price_str)
    try:
        await state.keychain.verify_authorize_key_tx(
            wallet_address=pending.wallet_address,
            key_id=pending.key_id,
            expected_monthly_price=monthly_price,
            currency=pending.currency,
            expected_expiry=pending.expiry,
            tx_hash=body.authorize_tx_hash,
        )
    except KeychainVerificationError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    period_start = datetime.now(UTC)
    memo = derive_subscription_memo(publisher.id, pending.wallet_address, period_start)
    try:
        charge = await state.keychain.submit_period_charge(
            access_key_private_key=pending.access_key_private_key,
            wallet_address=pending.wallet_address,
            recipient=pending.recipient,
            currency=pending.currency,
            monthly_price=monthly_price,
            memo=memo,
        )
    except PeriodChargeError as err:
        # Charge before persistence: failure leaves no authorization, no key
        # row, no period row. The on-chain authorize_key tx is unaffected;
        # client may submit revoke_key to recover gas.
        raise HTTPException(status_code=502, detail=str(err)) from err
    encrypted = state.keystore.encrypt(
        bytes.fromhex(pending.access_key_private_key.removeprefix("0x"))
    )
    authorization = insert_authorization_with_key(
        state.engine,
        wallet_address=pending.wallet_address,
        publisher_id=pending.publisher_id,
        key_id=pending.key_id,
        expiry=pending.expiry,
        authorize_tx_hash=body.authorize_tx_hash,
        encrypted_key=encrypted,
    )
    period = insert_subscription_period(
        state.engine,
        SubscriptionPeriod(
            id=uuid4(),
            wallet_address=pending.wallet_address,
            publisher_id=publisher.id,
            period_start=period_start,
            period_end=period_start + timedelta(seconds=pending.period_seconds),
            payment_reference=charge.payment_reference,
            amount=monthly_price,
            currency=pending.currency,
            network=state.tempo_network,
            receipt=receipt_payload(
                tx_hash=charge.payment_reference,
                block_number=charge.block_number,
                network=state.tempo_network,
                charged_at=period_start,
            ),
        ),
    )
    return _build_subscription_response(
        handle=handle,
        authorization=authorization,
        current_period=period,
    )


@router.delete("/api/subscriptions/{handle}", status_code=200)
def cancel_subscription(
    handle: str,
    state: Annotated[AppState, Depends(get_state)],
    principal: Annotated[WalletPrincipal, Depends(require_wallet_principal)],
) -> SubscriptionResponse:
    """Mark the authorization cancelled and surface the revoke_key calldata."""
    publisher = get_publisher_by_handle(state.engine, handle)
    if publisher is None:
        raise HTTPException(status_code=404, detail="Publisher not found")
    authorization = get_active_authorization(
        state.engine, principal.wallet_address, publisher.id
    )
    if authorization is None:
        raise HTTPException(status_code=404, detail="No active subscription")
    mark_authorization_status(state.engine, authorization.id, "cancelled")
    cancelled = SubscriptionAuthorization(
        id=authorization.id,
        wallet_address=authorization.wallet_address,
        publisher_id=authorization.publisher_id,
        key_id=authorization.key_id,
        expiry=authorization.expiry,
        status="cancelled",
        authorize_tx_hash=authorization.authorize_tx_hash,
    )
    current_period = get_active_subscription(
        state.engine,
        principal.wallet_address,
        publisher.id,
        datetime.now(UTC),
    )
    return _build_subscription_response(
        handle=handle,
        authorization=cancelled,
        current_period=current_period,
    )


@router.get("/api/subscriptions/{handle}", status_code=200)
def get_subscription(
    handle: str,
    state: Annotated[AppState, Depends(get_state)],
    principal: Annotated[WalletPrincipal, Depends(require_wallet_principal)],
) -> SubscriptionResponse:
    """Return the wallet's authorization + current-period status for a publisher."""
    publisher = get_publisher_by_handle(state.engine, handle)
    if publisher is None:
        raise HTTPException(status_code=404, detail="Publisher not found")
    authorization = get_active_authorization(
        state.engine, principal.wallet_address, publisher.id
    )
    if authorization is None:
        raise HTTPException(status_code=404, detail="No subscription found")
    current_period = get_active_subscription(
        state.engine,
        principal.wallet_address,
        publisher.id,
        datetime.now(UTC),
    )
    return _build_subscription_response(
        handle=handle,
        authorization=authorization,
        current_period=current_period,
    )


def _call_payload(target: str, calldata: bytes) -> CallPayload:
    """Convert raw calldata into a JSON-friendly CallPayload."""
    return CallPayload(to=target, data="0x" + calldata.hex())


def _build_subscription_response(
    *,
    handle: str,
    authorization: SubscriptionAuthorization,
    current_period: SubscriptionPeriod | None,
) -> SubscriptionResponse:
    """Materialize a SubscriptionResponse from persisted records."""
    period_response: SubscriptionPeriodResponse | None = None
    if current_period is not None:
        period_response = SubscriptionPeriodResponse(
            period_start=current_period.period_start,
            period_end=current_period.period_end,
            payment_reference=current_period.payment_reference,
            receipt=current_period.receipt,
        )
    revoke_call: CallPayload | None = None
    if authorization.status in ("cancelled", "active"):
        revoke_call = _call_payload(
            ACCOUNT_KEYCHAIN_ADDRESS,
            build_revoke_key_call(key_id=authorization.key_id).data,
        )
    return SubscriptionResponse(
        publisher_handle=handle,
        key_id=authorization.key_id,
        status=authorization.status,
        expiry=authorization.expiry,
        current_period=period_response,
        revoke_call=revoke_call,
    )


# Keep `to_base_units` reachable for callers that import via this module.
__all__ = [
    "router",
    "to_base_units",
    "PERIOD_SECONDS_30_DAYS",
]

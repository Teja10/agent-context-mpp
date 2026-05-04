from datetime import UTC, datetime
from hashlib import sha256
from typing import Annotated

from eth_account import Account
from eth_account.messages import encode_defunct
from eth_utils.exceptions import ValidationError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from mpp import Challenge, Receipt

from app.auth import parse_wallet_address
from app.db.queries import (
    get_active_subscription,
    get_article_by_slug,
    get_publisher_by_id,
    insert_one_time_purchase,
)
from app.db.records import OneTimePurchase
from app.models import ContextPackage
from app.state import AppState, get_state

router = APIRouter()


@router.get("/articles/{slug}/context", response_model=ContextPackage)
async def get_article_context(
    slug: str,
    request: Request,
    response: Response,
    state: Annotated[AppState, Depends(get_state)],
) -> ContextPackage | Response:
    """Return paid context for one loaded article."""
    article = get_article_by_slug(state.engine, slug)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")

    publisher = get_publisher_by_id(state.engine, article.publisher_id)
    if publisher is None:
        raise RuntimeError(f"Article {article.id} has no publisher")
    if publisher.status == "disabled":
        raise HTTPException(status_code=403, detail="Publisher is disabled")

    assert article.price is not None
    assert article.summary is not None
    assert article.key_claims is not None
    assert article.allowed_excerpts is not None
    assert article.suggested_citation is not None
    assert article.license is not None

    authorization = request.headers.get("Authorization")
    wallet_address = _try_wallet_proof(
        authorization, state.mpp.realm, state.mpp.secret_key
    )
    if wallet_address is not None:
        sub = get_active_subscription(
            state.engine, wallet_address, publisher.id, datetime.now(UTC)
        )
        if sub is not None:
            response.headers["Payment-Receipt"] = _subscription_receipt_header(
                sub.receipt
            )
            return ContextPackage(
                summary=article.summary,
                key_claims=article.key_claims,
                allowed_excerpts=article.allowed_excerpts,
                suggested_citation=article.suggested_citation,
                license=article.license,
                receipt=sub.receipt,
            )
        # Identified but no subscription: drop the WalletProof header so MPP
        # doesn't try to interpret it as a payment credential. Caller will
        # see a fresh PPV challenge.
        authorization = None

    result = await state.mpp.charge(
        authorization,
        str(article.price),
        memo=_context_memo(article.slug),
        recipient=article.publisher_recipient_address,
    )
    if isinstance(result, Challenge):
        return Response(
            status_code=402,
            headers={"WWW-Authenticate": result.to_www_authenticate(state.mpp.realm)},
        )

    credential, receipt = result
    response.headers["Payment-Receipt"] = receipt.to_payment_receipt()
    if credential.source is None:
        raise ValueError("Credential source missing after successful charge")
    payer_address = parse_wallet_address(credential.source)
    purchase = insert_one_time_purchase(
        state.engine,
        OneTimePurchase(
            article_slug=article.slug,
            wallet_address=payer_address,
            payment_reference=receipt.reference,
            amount=article.price,
            currency=state.pathusd_address,
            network=state.tempo_network,
            recipient_wallet=article.publisher_recipient_address.lower(),
            receipt=_receipt_payload(receipt),
        ),
        article.id,
    )
    return ContextPackage(
        summary=article.summary,
        key_claims=article.key_claims,
        allowed_excerpts=article.allowed_excerpts,
        suggested_citation=article.suggested_citation,
        license=article.license,
        receipt=purchase.receipt,
    )


def _context_memo(slug: str) -> str:
    return "0x" + sha256(slug.encode()).hexdigest()


def _receipt_payload(receipt: Receipt) -> dict[str, str]:
    payload: dict[str, str] = {
        "status": receipt.status,
        "timestamp": receipt.timestamp.isoformat(),
        "reference": receipt.reference,
        "method": receipt.method,
    }
    if receipt.external_id is not None:
        payload["external_id"] = receipt.external_id
    return payload


def _try_wallet_proof(
    authorization: str | None, realm: str, secret_key: str
) -> str | None:
    """Recover the wallet from a WalletProof header. None for any other scheme."""
    if authorization is None:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0] != "WalletProof":
        return None
    payload = parts[1].split(".", 1)
    if len(payload) != 2:
        return None
    nonce, signature = payload
    challenge = Challenge(
        id=nonce, method="tempo", intent="auth", request={}, realm=realm
    )
    if not challenge.verify(secret_key, realm):
        return None
    try:
        message = encode_defunct(text=nonce)
        raw_sig = signature.removeprefix("0x")
        recovered: str = Account.recover_message(
            message, signature=bytes.fromhex(raw_sig)
        )
    except (ValueError, ValidationError):
        return None
    return recovered.lower()


def _subscription_receipt_header(receipt: dict[str, str]) -> str:
    """Serialize a stored subscription receipt to MPP's Payment-Receipt format.

    Subscription receipts use the same wire format as PPV receipts so a single
    ``Receipt.from_payment_receipt(...)`` parser works for both code paths.
    """
    return Receipt(
        status="success",
        timestamp=datetime.fromisoformat(receipt["timestamp"]),
        reference=receipt["reference"],
        method=receipt.get("method", "tempo-access-key"),
        external_id=receipt.get("block_number"),
    ).to_payment_receipt()

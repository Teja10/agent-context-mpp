from hashlib import sha256
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from mpp import Challenge, Receipt

from app.auth import parse_wallet_address
from app.db.queries import (
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

    authorization = request.headers.get("Authorization")
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

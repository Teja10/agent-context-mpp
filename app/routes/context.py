from hashlib import sha256

from fastapi import APIRouter, HTTPException, Request, Response
from mpp import Challenge, Receipt
from mpp.server.mpp import Mpp
from sqlalchemy.engine import Engine

from app.db import OneTimePurchase, get_article_by_slug, insert_one_time_purchase
from app.models import ContextPackage

router = APIRouter()

_engine: Engine | None = None
_mpp: Mpp | None = None
_currency: str | None = None
_network: str | None = None


def set_context(
    engine: Engine,
    mpp: Mpp,
    currency: str,
    network: str,
) -> None:
    """Set context route resources loaded during application startup."""
    global _engine, _mpp, _currency, _network
    _engine = engine
    _mpp = mpp
    _currency = currency
    _network = network


@router.get("/articles/{slug}/context", response_model=ContextPackage)
async def get_article_context(
    slug: str, request: Request, response: Response
) -> ContextPackage | Response:
    """Return paid context for one loaded article."""
    engine = _loaded_engine()
    article = get_article_by_slug(engine, slug)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")

    mpp = _loaded_mpp()
    authorization = request.headers.get("Authorization")
    result = await mpp.charge(
        authorization,
        str(article.price),
        memo=_context_memo(article.slug),
    )
    if isinstance(result, Challenge):
        return Response(
            status_code=402,
            headers={"WWW-Authenticate": result.to_www_authenticate(mpp.realm)},
        )

    credential, receipt = result
    response.headers["Payment-Receipt"] = receipt.to_payment_receipt()
    payer_address = _payer_address(credential.source)
    purchase = insert_one_time_purchase(
        engine,
        OneTimePurchase(
            article_slug=article.slug,
            wallet_address=payer_address,
            payment_reference=receipt.reference,
            amount=article.price,
            currency=_loaded_currency(),
            network=_loaded_network(),
            receipt=_receipt_payload(receipt),
        ),
    )
    purchased_article = get_article_by_slug(engine, purchase.article_slug)
    if purchased_article is None:
        raise RuntimeError("Purchased article was not found")
    return ContextPackage(
        summary=purchased_article.summary,
        key_claims=purchased_article.key_claims,
        allowed_excerpts=purchased_article.allowed_excerpts,
        suggested_citation=purchased_article.suggested_citation,
        license=purchased_article.license,
        receipt=purchase.receipt,
    )


def _loaded_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("Database engine was not loaded during startup")
    return _engine


def _loaded_mpp() -> Mpp:
    if _mpp is None:
        raise RuntimeError("MPP was not loaded during startup")
    return _mpp


def _loaded_currency() -> str:
    if _currency is None:
        raise RuntimeError("Currency was not loaded during startup")
    return _currency


def _loaded_network() -> str:
    if _network is None:
        raise RuntimeError("Network was not loaded during startup")
    return _network


def _payer_address(source: str | None) -> str:
    if source is None or source == "":
        raise ValueError("Credential source is required")
    address = source.rsplit(":", maxsplit=1)[-1]
    if address == "":
        raise ValueError("Credential source must include a payer address")
    return address


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

from hashlib import sha256
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from mpp import Challenge, Receipt
from mpp.server.mpp import Mpp
from pydantic import TypeAdapter

from app.articles import Article
from app.db import Purchase, insert_purchase
from app.models import ContextPackage

router = APIRouter()
RECEIPT_PAYLOAD_ADAPTER = TypeAdapter(dict[str, str])

_articles: dict[str, Article] | None = None
_mpp: Mpp | None = None
_database_path: Path | None = None
_currency: str | None = None
_network: str | None = None


def set_context(
    articles: dict[str, Article],
    mpp: Mpp,
    database_path: Path,
    currency: str,
    network: str,
) -> None:
    """Set context route resources loaded during application startup."""
    global _articles, _mpp, _database_path, _currency, _network
    _articles = articles
    _mpp = mpp
    _database_path = database_path
    _currency = currency
    _network = network


@router.get("/articles/{slug}/context", response_model=ContextPackage)
async def get_article_context(
    slug: str, request: Request, response: Response
) -> ContextPackage | Response:
    """Return paid context for one loaded article."""
    articles = _loaded_articles()
    if slug not in articles:
        raise HTTPException(status_code=404, detail="Article not found")

    mpp = _loaded_mpp()
    article = articles[slug]
    authorization = request.headers.get("Authorization")
    result = await mpp.charge(
        authorization,
        article.price,
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
    purchase = insert_purchase(
        _loaded_database_path(),
        Purchase(
            article_slug=article.slug,
            payer_address=payer_address,
            tx_hash=receipt.reference,
            amount=article.price,
            currency=_loaded_currency(),
            network=_loaded_network(),
            receipt_json=RECEIPT_PAYLOAD_ADAPTER.dump_json(
                _receipt_payload(receipt)
            ).decode(),
        ),
    )
    purchased_article = articles[purchase.article_slug]
    return ContextPackage(
        summary=purchased_article.summary,
        key_claims=purchased_article.key_claims,
        allowed_excerpts=purchased_article.allowed_excerpts,
        suggested_citation=purchased_article.suggested_citation,
        license=purchased_article.license,
        receipt=RECEIPT_PAYLOAD_ADAPTER.validate_json(purchase.receipt_json),
    )


def _loaded_articles() -> dict[str, Article]:
    if _articles is None:
        raise RuntimeError("Articles were not loaded during startup")
    return _articles


def _loaded_mpp() -> Mpp:
    if _mpp is None:
        raise RuntimeError("MPP was not loaded during startup")
    return _mpp


def _loaded_database_path() -> Path:
    if _database_path is None:
        raise RuntimeError("Database path was not loaded during startup")
    return _database_path


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

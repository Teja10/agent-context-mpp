from app.db import Purchase, insert_purchase
from app.models import ContextPackage
from conftest import (
    ARTICLE_SLUG,
    CONTEXT_SLUG,
    CURRENCY,
    NETWORK,
    PAID_HEADERS,
    RECEIPT_JSON,
    TX_HASH,
    RouteClient,
    purchase_count,
)


def test_unknown_slug_returns_404_before_charge(paid_client: RouteClient) -> None:
    response = paid_client.client.get("/articles/unknown/context", headers=PAID_HEADERS)

    assert response.status_code == 404
    assert paid_client.mpp.calls == []


def test_duplicate_tx_hash_for_different_slug_returns_existing_context(
    paid_client: RouteClient,
) -> None:
    existing_article = paid_client.articles[ARTICLE_SLUG]
    requested_article = paid_client.articles[CONTEXT_SLUG]
    insert_purchase(
        paid_client.database_path,
        Purchase(
            article_slug=existing_article.slug,
            payer_address="0xoriginal",
            tx_hash=TX_HASH,
            amount=existing_article.price,
            currency=CURRENCY,
            network=NETWORK,
            receipt_json=RECEIPT_JSON,
        ),
    )

    response = paid_client.client.get(
        f"/articles/{requested_article.slug}/context", headers=PAID_HEADERS
    )

    assert response.status_code == 200
    context = ContextPackage.model_validate(response.json())
    assert context.summary == existing_article.summary
    assert context.key_claims == existing_article.key_claims
    assert purchase_count(paid_client.database_path) == 1

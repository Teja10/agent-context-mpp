import pytest

from app.db.queries import insert_one_time_purchase
from app.db.records import OneTimePurchase
from conftest import (
    ARTICLE_ID,
    ARTICLE_SLUG,
    CONTEXT_SLUG,
    CURRENCY,
    NETWORK,
    PAID_HEADERS,
    TX_HASH,
    RouteClient,
    purchase_count,
)


def test_unknown_slug_returns_404_before_charge(paid_client: RouteClient) -> None:
    response = paid_client.client.get("/articles/unknown/context", headers=PAID_HEADERS)

    assert response.status_code == 404
    assert paid_client.mpp.calls == []


def test_duplicate_payment_reference_for_different_slug_hard_fails(
    paid_client: RouteClient,
) -> None:
    requested_article = paid_client.articles[CONTEXT_SLUG]
    article_price = paid_client.articles[ARTICLE_SLUG].price
    assert article_price is not None
    insert_one_time_purchase(
        paid_client.engine,
        OneTimePurchase(
            article_slug=ARTICLE_SLUG,
            wallet_address="0xoriginal",
            payment_reference=TX_HASH,
            amount=article_price,
            currency=CURRENCY,
            network=NETWORK,
            receipt={"status": "original"},
        ),
        ARTICLE_ID,
    )

    with pytest.raises(
        RuntimeError,
        match="Payment reference is bound to different purchase details",
    ):
        paid_client.client.get(
            f"/articles/{requested_article.slug}/context", headers=PAID_HEADERS
        )

    assert purchase_count(paid_client.engine) == 1

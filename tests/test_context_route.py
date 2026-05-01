import pytest

from app.db.queries import (
    insert_one_time_purchase,
    lookup_purchase_by_payment_reference,
)
from app.db.records import OneTimePurchase
from conftest import (
    ARTICLE_B_ID,
    ARTICLE_B_SLUG,
    ARTICLE_ID,
    ARTICLE_SLUG,
    CONTEXT_SLUG,
    CURRENCY,
    NETWORK,
    PAID_HEADERS,
    PUBLISHER_B_RECIPIENT,
    PUBLISHER_RECIPIENT,
    TX_HASH,
    ChargeCall,
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
    insert_one_time_purchase(
        paid_client.engine,
        OneTimePurchase(
            article_slug=ARTICLE_SLUG,
            wallet_address="0xoriginal",
            payment_reference=TX_HASH,
            amount=paid_client.articles[ARTICLE_SLUG].price,
            currency=CURRENCY,
            network=NETWORK,
            recipient_wallet=PUBLISHER_RECIPIENT.lower(),
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


def test_unpaid_access_returns_402_with_correct_recipient(
    challenge_client: RouteClient,
) -> None:
    article = challenge_client.articles[ARTICLE_SLUG]

    challenge_client.client.get(f"/articles/{ARTICLE_SLUG}/context")

    assert challenge_client.mpp.calls == [
        ChargeCall(
            authorization=None,
            amount=str(article.price),
            memo="0x4709280c7c375e35bb5c1dc5beba9fd25ddc8743c6959facf650ef0c6e3ab785",
            recipient=PUBLISHER_RECIPIENT,
        )
    ]


def test_paid_context_persists_recipient_wallet(
    paid_client: RouteClient,
) -> None:
    paid_client.client.get(f"/articles/{ARTICLE_SLUG}/context", headers=PAID_HEADERS)

    purchase = lookup_purchase_by_payment_reference(paid_client.engine, TX_HASH)
    assert purchase is not None
    assert purchase.recipient_wallet == PUBLISHER_RECIPIENT.lower()


def test_publisher_mismatch_payment_reference_hard_fails(
    paid_client: RouteClient,
) -> None:
    insert_one_time_purchase(
        paid_client.engine,
        OneTimePurchase(
            article_slug=ARTICLE_B_SLUG,
            wallet_address="0xpayer",
            payment_reference=TX_HASH,
            amount=paid_client.articles[ARTICLE_B_SLUG].price,
            currency=CURRENCY,
            network=NETWORK,
            recipient_wallet=PUBLISHER_B_RECIPIENT.lower(),
            receipt={"status": "success"},
        ),
        ARTICLE_B_ID,
    )

    with pytest.raises(
        RuntimeError,
        match="Payment reference is bound to different purchase details",
    ):
        paid_client.client.get(
            f"/articles/{ARTICLE_SLUG}/context", headers=PAID_HEADERS
        )

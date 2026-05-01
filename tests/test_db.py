from decimal import Decimal

import pytest
from sqlalchemy.engine import Engine

from app.db.queries import (
    insert_one_time_purchase,
    list_articles,
    lookup_purchase_by_payment_reference,
)
from app.db.records import OneTimePurchase
from conftest import (
    ARTICLE_ID,
    ARTICLE_SLUG,
    CONTEXT_ID,
    RECEIPT_PAYLOAD,
    TX_HASH,
    purchase_count,
)


def purchase() -> OneTimePurchase:
    """Return a purchase record for storage tests."""
    return OneTimePurchase(
        article_slug=ARTICLE_SLUG,
        wallet_address="0xpayer",
        payment_reference=TX_HASH,
        amount=Decimal("1.25"),
        currency="PATHUSD",
        network="tempo",
        receipt=RECEIPT_PAYLOAD,
    )


def test_list_articles_returns_seeded_postgres_articles(engine: Engine) -> None:
    articles = list_articles(engine)

    assert [article.slug for article in articles] == [
        "ai-agent-payments",
        "context-for-machines",
        "decentralized-identity",
    ]
    assert articles[0].key_claims == ["AI Agent Payments claim."]


def test_insert_purchase_stores_decimal_and_jsonb(engine: Engine) -> None:
    stored_purchase = purchase()

    insert_one_time_purchase(engine, stored_purchase, ARTICLE_ID)

    assert (
        lookup_purchase_by_payment_reference(engine, stored_purchase.payment_reference)
        == stored_purchase
    )


def test_same_payment_reference_replay_returns_existing_purchase(
    engine: Engine,
) -> None:
    stored_purchase = purchase()

    insert_one_time_purchase(engine, stored_purchase, ARTICLE_ID)

    assert (
        insert_one_time_purchase(engine, stored_purchase, ARTICLE_ID) == stored_purchase
    )
    assert purchase_count(engine) == 1


def test_duplicate_payment_reference_for_different_article_hard_fails(
    engine: Engine,
) -> None:
    stored_purchase = purchase()
    duplicate_purchase = OneTimePurchase(
        article_slug="context-for-machines",
        wallet_address="0xother",
        payment_reference=stored_purchase.payment_reference,
        amount=Decimal("9.99"),
        currency="PATHUSD",
        network="tempo",
        receipt={"status": "duplicate"},
    )

    insert_one_time_purchase(engine, stored_purchase, ARTICLE_ID)

    with pytest.raises(
        RuntimeError,
        match="Payment reference is bound to different purchase details",
    ):
        insert_one_time_purchase(engine, duplicate_purchase, CONTEXT_ID)

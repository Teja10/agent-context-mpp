"""One-time purchase query functions."""

from typing import Optional
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine, RowMapping

from app.db.queries import upsert_wallet_principal
from app.db.records import OneTimePurchase
from app.db.schema import articles, one_time_purchases


def insert_one_time_purchase(
    engine: Engine,
    purchase: OneTimePurchase,
    article_id: UUID,
) -> OneTimePurchase:
    """Persist a wallet principal and one-time purchase."""
    upsert_wallet_principal(engine, purchase.wallet_address)
    with engine.begin() as connection:
        result = connection.execute(
            insert(one_time_purchases)
            .values(
                id=text("gen_random_uuid()"),
                wallet_address=purchase.wallet_address,
                article_id=article_id,
                payment_reference=purchase.payment_reference,
                amount=purchase.amount,
                currency=purchase.currency,
                network=purchase.network,
                recipient_wallet=purchase.recipient_wallet,
                receipt=purchase.receipt,
                created_at=text("now()"),
            )
            .on_conflict_do_nothing()
        )
    if result.rowcount == 1:
        return purchase
    existing_purchase = lookup_purchase_by_payment_reference(
        engine, purchase.payment_reference
    )
    if existing_purchase is None:
        raise RuntimeError("Wallet already purchased this article")
    if existing_purchase != purchase:
        raise RuntimeError("Payment reference is bound to different purchase details")
    return existing_purchase


def get_one_time_purchase_for_article(
    engine: Engine,
    wallet_address: str,
    article_id: UUID,
) -> Optional[OneTimePurchase]:
    """Return the wallet's existing one-time purchase for an article, if any.

    The unique ``(wallet_address, article_id)`` constraint guarantees at most
    one row matches, so this lookup encodes "has this wallet ever paid for
    this article?" — the persistent-PPV entitlement.
    """
    with engine.connect() as connection:
        row = (
            connection.execute(
                select(
                    articles.c.slug.label("article_slug"),
                    one_time_purchases.c.wallet_address,
                    one_time_purchases.c.payment_reference,
                    one_time_purchases.c.amount,
                    one_time_purchases.c.currency,
                    one_time_purchases.c.network,
                    one_time_purchases.c.recipient_wallet,
                    one_time_purchases.c.receipt,
                )
                .select_from(
                    one_time_purchases.join(
                        articles, one_time_purchases.c.article_id == articles.c.id
                    )
                )
                .where(one_time_purchases.c.wallet_address == wallet_address)
                .where(one_time_purchases.c.article_id == article_id)
            )
            .mappings()
            .one_or_none()
        )
    if row is None:
        return None
    return _one_time_purchase(row)


def lookup_purchase_by_payment_reference(
    engine: Engine,
    payment_reference: str,
) -> Optional[OneTimePurchase]:
    """Return the purchase stored for a payment reference."""
    with engine.connect() as connection:
        row = (
            connection.execute(
                select(
                    articles.c.slug.label("article_slug"),
                    one_time_purchases.c.wallet_address,
                    one_time_purchases.c.payment_reference,
                    one_time_purchases.c.amount,
                    one_time_purchases.c.currency,
                    one_time_purchases.c.network,
                    one_time_purchases.c.recipient_wallet,
                    one_time_purchases.c.receipt,
                )
                .select_from(
                    one_time_purchases.join(
                        articles,
                        one_time_purchases.c.article_id == articles.c.id,
                    )
                )
                .where(one_time_purchases.c.payment_reference == payment_reference)
            )
            .mappings()
            .one_or_none()
        )
    if row is None:
        return None
    return _one_time_purchase(row)


def _one_time_purchase(row: RowMapping) -> OneTimePurchase:
    return OneTimePurchase(
        article_slug=row["article_slug"],
        wallet_address=row["wallet_address"],
        payment_reference=row["payment_reference"],
        amount=row["amount"],
        currency=row["currency"],
        network=row["network"],
        recipient_wallet=row["recipient_wallet"],
        receipt=dict(row["receipt"]),
    )

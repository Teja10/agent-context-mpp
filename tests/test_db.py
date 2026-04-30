from pathlib import Path
import sqlite3

from app.db import (
    Purchase,
    initialize_database,
    insert_purchase,
    lookup_purchase_by_tx_hash,
)


def purchase() -> Purchase:
    """Return a purchase record for storage tests."""
    return Purchase(
        article_slug="context-for-machines",
        payer_address="0xpayer",
        tx_hash="0xtx",
        amount="1.25",
        currency="PATHUSD",
        network="base",
        receipt_json='{"status":"ok"}',
    )


def test_initialize_database_creates_purchase_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "purchases.db"

    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        columns = connection.execute("PRAGMA table_info(purchases)").fetchall()

    column_names = [column["name"] for column in columns]
    assert column_names == [
        "id",
        "article_slug",
        "payer_address",
        "tx_hash",
        "amount",
        "currency",
        "network",
        "receipt_json",
        "created_at",
    ]


def test_insert_purchase_stores_amount_as_text(tmp_path: Path) -> None:
    database_path = tmp_path / "purchases.db"
    stored_purchase = purchase()

    initialize_database(database_path)
    insert_purchase(database_path, stored_purchase)

    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT amount, typeof(amount) AS amount_type FROM purchases WHERE tx_hash = ?",
            [stored_purchase.tx_hash],
        ).fetchone()

    assert row is not None
    assert row["amount"] == "1.25"
    assert row["amount_type"] == "text"


def test_lookup_purchase_by_tx_hash_returns_persisted_purchase(tmp_path: Path) -> None:
    database_path = tmp_path / "purchases.db"
    stored_purchase = purchase()

    initialize_database(database_path)
    insert_purchase(database_path, stored_purchase)

    assert (
        lookup_purchase_by_tx_hash(database_path, stored_purchase.tx_hash)
        == stored_purchase
    )


def test_duplicate_tx_hash_returns_existing_persisted_purchase(tmp_path: Path) -> None:
    database_path = tmp_path / "purchases.db"
    existing_purchase = purchase()
    duplicate_purchase = Purchase(
        article_slug="ai-agent-payments",
        payer_address="0xother",
        tx_hash=existing_purchase.tx_hash,
        amount="9.99",
        currency="PATHUSD",
        network="base",
        receipt_json='{"status":"duplicate"}',
    )

    initialize_database(database_path)
    insert_purchase(database_path, existing_purchase)

    assert insert_purchase(database_path, duplicate_purchase) == existing_purchase

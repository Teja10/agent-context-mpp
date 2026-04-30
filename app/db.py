from dataclasses import dataclass
from pathlib import Path
import sqlite3


@dataclass(frozen=True)
class Purchase:
    """Purchase record persisted by transaction hash."""

    article_slug: str
    payer_address: str
    tx_hash: str
    amount: str
    currency: str
    network: str
    receipt_json: str


def initialize_database(database_path: Path) -> None:
    """Create the purchase storage schema."""
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_slug TEXT NOT NULL,
                payer_address TEXT NOT NULL,
                tx_hash TEXT UNIQUE,
                amount TEXT NOT NULL,
                currency TEXT NOT NULL,
                network TEXT NOT NULL,
                receipt_json TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def insert_purchase(database_path: Path, purchase: Purchase) -> Purchase:
    """Insert a purchase or return the existing record for the same transaction."""
    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO purchases (
                article_slug,
                payer_address,
                tx_hash,
                amount,
                currency,
                network,
                receipt_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tx_hash) DO NOTHING
            """,
            [
                purchase.article_slug,
                purchase.payer_address,
                purchase.tx_hash,
                purchase.amount,
                purchase.currency,
                purchase.network,
                purchase.receipt_json,
            ],
        )
    if cursor.rowcount == 1:
        return purchase
    existing_purchase = lookup_purchase_by_tx_hash(database_path, purchase.tx_hash)
    if existing_purchase is None:
        raise RuntimeError("Purchase conflict did not return an existing row")
    return existing_purchase


def lookup_purchase_by_tx_hash(database_path: Path, tx_hash: str) -> Purchase | None:
    """Return the purchase stored for a transaction hash."""
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT
                article_slug,
                payer_address,
                tx_hash,
                amount,
                currency,
                network,
                receipt_json
            FROM purchases
            WHERE tx_hash = ?
            """,
            [tx_hash],
        ).fetchone()
    if row is None:
        return None
    return Purchase(
        article_slug=row["article_slug"],
        payer_address=row["payer_address"],
        tx_hash=row["tx_hash"],
        amount=row["amount"],
        currency=row["currency"],
        network=row["network"],
        receipt_json=row["receipt_json"],
    )

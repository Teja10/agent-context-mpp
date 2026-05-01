"""Database package exposing schema, records, and queries."""

from app.db.queries import (
    create_database_engine,
    get_article_by_slug,
    insert_one_time_purchase,
    list_article_metadata,
    list_articles,
    lookup_purchase_by_payment_reference,
    verify_database,
)
from app.db.records import ArticleRecord, OneTimePurchase
from app.db.schema import articles, metadata, publishers

__all__ = [
    "ArticleRecord",
    "OneTimePurchase",
    "articles",
    "create_database_engine",
    "get_article_by_slug",
    "insert_one_time_purchase",
    "list_article_metadata",
    "list_articles",
    "lookup_purchase_by_payment_reference",
    "metadata",
    "publishers",
    "verify_database",
]

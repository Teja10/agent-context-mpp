"""Typed dataclass records mapped from database rows."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from app.models import ArticleMetadata


@dataclass(frozen=True)
class PublisherRecord:
    """Publisher loaded from Postgres."""

    id: UUID
    handle: str
    display_name: str
    recipient_address: str


@dataclass(frozen=True)
class ArticleRecord:
    """Article content loaded from Postgres."""

    id: UUID
    title: str
    author: str
    published_date: date
    price: Decimal
    license: str
    summary: str
    tags: list[str]
    key_claims: list[str]
    allowed_excerpts: list[str]
    suggested_citation: str
    slug: str
    body: str
    publisher_recipient_address: str

    @property
    def metadata(self) -> ArticleMetadata:
        """Return public metadata for this article."""
        return ArticleMetadata(
            title=self.title,
            author=self.author,
            published_date=self.published_date,
            price=str(self.price),
            slug=self.slug,
        )


@dataclass(frozen=True)
class OneTimePurchase:
    """One-time article purchase stored by payment reference.

    Frozen: returned from lookups and compared for equality in idempotency checks.
    """

    article_slug: str
    wallet_address: str
    payment_reference: str
    amount: Decimal
    currency: str
    network: str
    recipient_wallet: str
    receipt: dict[str, str]

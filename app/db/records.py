"""Typed dataclass records mapped from database rows."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from app.models import ArticleMetadata


@dataclass(frozen=True)
class PublisherRecord:
    """Publisher loaded from Postgres."""

    id: UUID
    handle: str
    display_name: str
    owner_address: str
    description: str
    status: str
    recipient_address: str
    default_article_price: Decimal
    default_subscription_price: Decimal


@dataclass(frozen=True)
class ArticleRecord:
    """Article content loaded from Postgres."""

    id: UUID
    publisher_id: UUID
    title: str
    status: str
    author: Optional[str]
    published_date: Optional[date]
    price: Optional[Decimal]
    license: Optional[str]
    summary: Optional[str]
    tags: Optional[list[str]]
    key_claims: Optional[list[str]]
    allowed_excerpts: Optional[list[str]]
    suggested_citation: Optional[str]
    slug: str
    body: str
    publisher_recipient_address: str

    @property
    def metadata(self) -> ArticleMetadata:
        """Return public metadata for this article."""
        assert self.author is not None
        assert self.published_date is not None
        assert self.price is not None
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


@dataclass(frozen=True)
class SubscriptionAuthorization:
    """On-chain access-key authorization granting Thoth periodic charge rights."""

    id: UUID
    wallet_address: str
    publisher_id: UUID
    key_id: str
    expiry: datetime
    status: str
    authorize_tx_hash: str


@dataclass(frozen=True)
class SubscriptionPeriod:
    """One paid subscription period: a single transferWithMemo receipt."""

    id: UUID
    wallet_address: str
    publisher_id: UUID
    period_start: datetime
    period_end: datetime
    payment_reference: str
    amount: Decimal
    currency: str
    network: str
    receipt: dict[str, str]


@dataclass(frozen=True)
class DueRenewal:
    """Authorization that needs a charge for the next period."""

    authorization_id: UUID
    wallet_address: str
    publisher_id: UUID
    key_id: str
    expiry: datetime
    last_period_end: datetime
    attempts: int
    last_attempt_at: Optional[datetime]

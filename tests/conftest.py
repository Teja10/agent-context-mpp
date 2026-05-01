from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
import os
from typing import cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mpp import Challenge, ChallengeEcho, Credential, Receipt
from mpp.server.mpp import Mpp
from sqlalchemy import insert, text
from sqlalchemy.engine import Engine

from app.db import (
    ArticleRecord,
    articles,
    create_database_engine,
    list_articles,
    publishers,
)
from app.routes import articles as article_routes
from app.routes import context, health
from app.state import AppState

ARTICLE_SLUG = "ai-agent-payments"
CONTEXT_SLUG = "context-for-machines"
TX_HASH = "0xtx"
CURRENCY = "PATHUSD"
NETWORK = "tempo"
PAID_HEADERS = {"Authorization": "paid"}
RECEIPT_PAYLOAD = {
    "status": "success",
    "timestamp": "2026-04-01T12:00:00+00:00",
    "reference": TX_HASH,
    "method": "tempo",
}
PUBLISHER_ID = UUID("11111111-1111-1111-1111-111111111111")
ARTICLE_ID = UUID("22222222-2222-2222-2222-222222222222")
CONTEXT_ID = UUID("33333333-3333-3333-3333-333333333333")
IDENTITY_ID = UUID("44444444-4444-4444-4444-444444444444")


@dataclass(frozen=True)
class ChargeCall:
    """MPP charge invocation captured by tests."""

    authorization: str | None
    amount: str
    memo: str


@dataclass(frozen=True)
class SuccessfulCharge:
    """Successful MPP charge result unpacked by the route."""

    credential: Credential
    receipt: Receipt

    def __iter__(self) -> Iterator[Credential | Receipt]:
        """Yield charge parts in the order returned by MPP."""
        yield self.credential
        yield self.receipt


class FakeMpp:
    """Fake MPP handler that returns a configured charge result."""

    def __init__(self, result: Challenge | SuccessfulCharge) -> None:
        self.realm = "agent-context"
        self.result = result
        self.calls: list[ChargeCall] = []

    async def charge(
        self, authorization: str | None, amount: str, *, memo: str
    ) -> Challenge | SuccessfulCharge:
        """Record a charge request and return the configured result."""
        self.calls.append(
            ChargeCall(authorization=authorization, amount=amount, memo=memo)
        )
        return self.result


@dataclass(frozen=True)
class RouteClient:
    """Test client and resources configured for route tests."""

    client: TestClient
    engine: Engine
    articles: dict[str, ArticleRecord]
    mpp: FakeMpp


@pytest.fixture
def engine() -> Iterator[Engine]:
    """Create a Postgres engine from the required test DATABASE_URL."""
    database_url = os.environ["DATABASE_URL"]
    if database_url == "":
        raise ValueError("DATABASE_URL must not be empty")
    engine = create_database_engine(database_url)
    _truncate_age10_tables(engine)
    _insert_article_catalog(engine)
    yield engine
    _truncate_age10_tables(engine)
    engine.dispose()


@pytest.fixture
def article_catalog(engine: Engine) -> dict[str, ArticleRecord]:
    """Return seeded article records for route tests."""
    return {article.slug: article for article in list_articles(engine)}


@pytest.fixture
def challenge() -> Challenge:
    """Return an MPP payment challenge."""
    return Challenge(
        id="challenge-id",
        method="tempo",
        intent="charge",
        request={},
        realm="agent-context",
    )


@pytest.fixture
def credential() -> Credential:
    """Return a credential with a payer source."""
    return Credential(
        challenge=ChallengeEcho(
            id="challenge-id",
            realm="agent-context",
            method="tempo",
            intent="charge",
            request="e30",
        ),
        payload={"authorization": "paid"},
        source="tempo:0xpayer",
    )


@pytest.fixture
def receipt() -> Receipt:
    """Return a successful payment receipt."""
    return Receipt(
        status="success",
        timestamp=datetime(2026, 4, 1, 12, 0, tzinfo=UTC),
        reference=TX_HASH,
        method="tempo",
    )


@pytest.fixture
def challenge_client(
    engine: Engine,
    article_catalog: dict[str, ArticleRecord],
    challenge: Challenge,
) -> RouteClient:
    """Return a route client backed by an MPP challenge response."""
    fake_mpp = FakeMpp(challenge)
    return _route_client(engine, article_catalog, fake_mpp)


@pytest.fixture
def paid_client(
    engine: Engine,
    article_catalog: dict[str, ArticleRecord],
    credential: Credential,
    receipt: Receipt,
) -> RouteClient:
    """Return a route client backed by a successful MPP charge."""
    fake_mpp = FakeMpp(SuccessfulCharge(credential=credential, receipt=receipt))
    return _route_client(engine, article_catalog, fake_mpp)


def purchase_count(engine: Engine) -> int:
    """Return the number of persisted one-time purchases."""
    with engine.connect() as connection:
        return cast(
            int,
            connection.execute(
                text("select count(*) from one_time_purchases")
            ).scalar_one(),
        )


def _route_client(
    engine: Engine,
    article_catalog: dict[str, ArticleRecord],
    fake_mpp: FakeMpp,
) -> RouteClient:
    app = FastAPI()
    app.state.ctx = AppState(
        engine=engine,
        mpp=cast(Mpp, fake_mpp),
        pathusd_address=CURRENCY,
        tempo_network=NETWORK,
    )
    app.include_router(health.router)
    app.include_router(article_routes.router)
    app.include_router(context.router)
    return RouteClient(
        client=TestClient(app),
        engine=engine,
        articles=article_catalog,
        mpp=fake_mpp,
    )


def _truncate_age10_tables(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                truncate table
                    feedback,
                    usage_events,
                    subscriptions,
                    one_time_purchases,
                    articles,
                    publishers,
                    wallet_principals
                restart identity cascade
                """
            )
        )


def _insert_article_catalog(engine: Engine) -> None:
    created_at = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(
            insert(publishers).values(
                id=PUBLISHER_ID,
                handle="agent-context-research",
                display_name="Agent Context Research",
                recipient_address="0x52908400098527886E0F7030069857D2E4169EE7",
                created_at=created_at,
            )
        )
        connection.execute(
            insert(articles),
            [
                _article_values(
                    ARTICLE_ID,
                    ARTICLE_SLUG,
                    "AI Agent Payments",
                    Decimal("0.25"),
                    created_at,
                ),
                _article_values(
                    CONTEXT_ID,
                    CONTEXT_SLUG,
                    "Context for Machines",
                    Decimal("1.25"),
                    created_at,
                ),
                _article_values(
                    IDENTITY_ID,
                    "decentralized-identity",
                    "Decentralized Identity",
                    Decimal("0.75"),
                    created_at,
                ),
            ],
        )


def _article_values(
    article_id: UUID,
    slug: str,
    title: str,
    price: Decimal,
    created_at: datetime,
) -> dict[str, object]:
    return {
        "id": article_id,
        "publisher_id": PUBLISHER_ID,
        "slug": slug,
        "title": title,
        "author": "Agent Context Research",
        "published_at": date(2026, 4, 29),
        "price": price,
        "license": "Context preview license",
        "summary": f"{title} summary.",
        "tags": ["mpp"],
        "key_claims": [f"{title} claim."],
        "allowed_excerpts": [f"{title} excerpt."],
        "suggested_citation": f"{title}.",
        "body": f"{title} body.",
        "created_at": created_at,
        "updated_at": created_at,
    }

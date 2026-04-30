from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import sqlite3
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mpp import Challenge, ChallengeEcho, Credential, Receipt
from mpp.server.mpp import Mpp

from app.articles import ARTICLES_DIR, Article, load_articles
from app.db import initialize_database
from app.routes import articles, context, health

ARTICLE_SLUG = "ai-agent-payments"
CONTEXT_SLUG = "context-for-machines"
TX_HASH = "0xtx"
RECEIPT_JSON = (
    '{"status":"success","timestamp":"2026-04-01T12:00:00+00:00",'
    '"reference":"0xtx","method":"tempo"}'
)
CURRENCY = "PATHUSD"
NETWORK = "tempo"
PAID_HEADERS = {"Authorization": "paid"}
RECEIPT_PAYLOAD = {
    "status": "success",
    "timestamp": "2026-04-01T12:00:00+00:00",
    "reference": TX_HASH,
    "method": "tempo",
}


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
    database_path: Path
    articles: dict[str, Article]
    mpp: FakeMpp


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    """Create and initialize a temporary purchase database."""
    path = tmp_path / "purchases.db"
    initialize_database(path)
    return path


@pytest.fixture
def article_catalog() -> dict[str, Article]:
    """Load real demo articles for route tests."""
    return load_articles(ARTICLES_DIR)


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
    database_path: Path,
    article_catalog: dict[str, Article],
    challenge: Challenge,
) -> RouteClient:
    """Return a route client backed by an MPP challenge response."""
    fake_mpp = FakeMpp(challenge)
    return _route_client(database_path, article_catalog, fake_mpp)


@pytest.fixture
def paid_client(
    database_path: Path,
    article_catalog: dict[str, Article],
    credential: Credential,
    receipt: Receipt,
) -> RouteClient:
    """Return a route client backed by a successful MPP charge."""
    fake_mpp = FakeMpp(SuccessfulCharge(credential=credential, receipt=receipt))
    return _route_client(database_path, article_catalog, fake_mpp)


def purchase_count(database_path: Path) -> int:
    """Return the number of persisted purchases."""
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT COUNT(*) AS purchase_count FROM purchases"
        ).fetchone()
        assert row is not None
        return cast(int, row["purchase_count"])


def _route_client(
    database_path: Path,
    article_catalog: dict[str, Article],
    fake_mpp: FakeMpp,
) -> RouteClient:
    articles.set_articles(article_catalog)
    context.set_context(
        articles=article_catalog,
        mpp=cast(Mpp, fake_mpp),
        database_path=database_path,
        currency=CURRENCY,
        network=NETWORK,
    )
    app = FastAPI()
    app.include_router(health.router)
    app.include_router(articles.router)
    app.include_router(context.router)
    return RouteClient(
        client=TestClient(app),
        database_path=database_path,
        articles=article_catalog,
        mpp=fake_mpp,
    )

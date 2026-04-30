from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
import sqlite3
from typing import cast

from fastapi import FastAPI
from fastapi.testclient import TestClient
from mpp import Challenge, ChallengeEcho, Credential, Receipt
from mpp.server.mpp import Mpp

from app.articles import Article
from app.db import (
    Purchase,
    initialize_database,
    insert_purchase,
    lookup_purchase_by_tx_hash,
)
from app.routes.context import router, set_context

ARTICLE_SLUG = "ai-agent-payments"
CONTEXT_SLUG = "context-for-machines"
TX_HASH = "0xtx"
RECEIPT_JSON = (
    '{"status":"success","timestamp":"2026-04-01T12:00:00+00:00",'
    '"reference":"0xtx","method":"tempo"}'
)


@dataclass(frozen=True)
class ChargeCall:
    """MPP charge invocation captured by tests."""

    authorization: str | None
    amount: str


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
        self, authorization: str | None, amount: str
    ) -> Challenge | SuccessfulCharge:
        """Record a charge request and return the configured result."""
        self.calls.append(ChargeCall(authorization=authorization, amount=amount))
        return self.result


def article(slug: str, price: str, summary: str) -> Article:
    """Return an article fixture for context route tests."""
    return Article(
        title=f"{slug} title",
        author="Tempo Labs",
        published_date=date(2026, 4, 1),
        price=price,
        license="CC-BY-4.0",
        summary=summary,
        key_claims=[f"{slug} claim"],
        allowed_excerpts=[f"{slug} excerpt"],
        suggested_citation=f"{slug} citation",
        slug=slug,
        body="Fixture article body",
    )


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


def receipt(tx_hash: str) -> Receipt:
    """Return a successful payment receipt."""
    return Receipt(
        status="success",
        timestamp=datetime(2026, 4, 1, 12, 0, tzinfo=UTC),
        reference=tx_hash,
        method="tempo",
    )


def challenge() -> Challenge:
    """Return an MPP payment challenge."""
    return Challenge(
        id="challenge-id",
        method="tempo",
        intent="charge",
        request={},
        realm="agent-context",
    )


def article_catalog(articles: list[Article]) -> dict[str, Article]:
    """Return articles keyed by slug."""
    return {loaded_article.slug: loaded_article for loaded_article in articles}


def make_client(
    tmp_path: Path,
    articles: dict[str, Article],
    fake_mpp: FakeMpp,
) -> TestClient:
    """Return a test client wired to fake route resources."""
    database_path = tmp_path / "purchases.db"
    initialize_database(database_path)
    set_context(
        articles=articles,
        mpp=cast(Mpp, fake_mpp),
        database_path=database_path,
        currency="PATHUSD",
        network="tempo",
    )
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def purchase_count(database_path: Path) -> int:
    """Return the number of persisted purchases."""
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT COUNT(*) AS purchase_count FROM purchases"
        ).fetchone()
        assert row is not None
        return cast(int, row["purchase_count"])


def test_unknown_slug_returns_404_before_charge(tmp_path: Path) -> None:
    paid_article = article(ARTICLE_SLUG, "1.25", "Paid context summary")
    fake_mpp = FakeMpp(SuccessfulCharge(credential(), receipt(TX_HASH)))
    client = make_client(
        tmp_path,
        article_catalog([paid_article]),
        fake_mpp,
    )

    response = client.get(
        "/articles/unknown/context", headers={"Authorization": "paid"}
    )

    assert response.status_code == 404
    assert fake_mpp.calls == []


def test_missing_authorization_returns_payment_challenge(tmp_path: Path) -> None:
    paid_article = article(ARTICLE_SLUG, "1.25", "Paid context summary")
    fake_mpp = FakeMpp(challenge())
    client = make_client(
        tmp_path,
        article_catalog([paid_article]),
        fake_mpp,
    )

    response = client.get(f"/articles/{ARTICLE_SLUG}/context")

    assert response.status_code == 402
    assert response.headers["WWW-Authenticate"].startswith("Payment ")
    assert fake_mpp.calls == [ChargeCall(authorization=None, amount="1.25")]


def test_successful_paid_response_persists_purchase_without_body(
    tmp_path: Path,
) -> None:
    paid_article = article(
        ARTICLE_SLUG,
        "1.25",
        "Paid context summary",
    )
    fake_mpp = FakeMpp(SuccessfulCharge(credential(), receipt(TX_HASH)))
    client = make_client(tmp_path, article_catalog([paid_article]), fake_mpp)
    database_path = tmp_path / "purchases.db"

    response = client.get(
        f"/articles/{ARTICLE_SLUG}/context",
        headers={"Authorization": "paid"},
    )

    response_body = response.json()
    assert response.status_code == 200
    assert response_body == {
        "summary": "Paid context summary",
        "key_claims": ["ai-agent-payments claim"],
        "allowed_excerpts": ["ai-agent-payments excerpt"],
        "suggested_citation": "ai-agent-payments citation",
        "license": "CC-BY-4.0",
        "receipt": {
            "status": "success",
            "timestamp": "2026-04-01T12:00:00+00:00",
            "reference": "0xtx",
            "method": "tempo",
        },
    }
    assert "body" not in response_body
    assert lookup_purchase_by_tx_hash(database_path, TX_HASH) == Purchase(
        article_slug=paid_article.slug,
        payer_address="0xpayer",
        tx_hash=TX_HASH,
        amount=paid_article.price,
        currency="PATHUSD",
        network="tempo",
        receipt_json=RECEIPT_JSON,
    )
    assert purchase_count(database_path) == 1


def test_duplicate_tx_hash_returns_existing_context_without_second_row(
    tmp_path: Path,
) -> None:
    existing_article = article(
        ARTICLE_SLUG,
        "1.25",
        "Existing purchase summary",
    )
    requested_article = article(
        CONTEXT_SLUG,
        "2.50",
        "Requested article summary",
    )
    fake_mpp = FakeMpp(SuccessfulCharge(credential(), receipt(TX_HASH)))
    client = make_client(
        tmp_path,
        article_catalog([existing_article, requested_article]),
        fake_mpp,
    )
    database_path = tmp_path / "purchases.db"
    insert_purchase(
        database_path,
        Purchase(
            article_slug=existing_article.slug,
            payer_address="0xoriginal",
            tx_hash=TX_HASH,
            amount=existing_article.price,
            currency="PATHUSD",
            network="tempo",
            receipt_json=RECEIPT_JSON,
        ),
    )

    response = client.get(
        f"/articles/{CONTEXT_SLUG}/context",
        headers={"Authorization": "paid"},
    )

    response_body = response.json()
    assert response.status_code == 200
    assert response_body["summary"] == "Existing purchase summary"
    assert response_body["key_claims"] == ["ai-agent-payments claim"]
    assert "body" not in response_body
    assert purchase_count(database_path) == 1

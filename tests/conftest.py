from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
import os
from typing import Optional, cast
from uuid import UUID

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mpp import Challenge, ChallengeEcho, Credential, Receipt
from mpp.server.mpp import Mpp
from sqlalchemy import insert, text
from sqlalchemy.engine import Engine

from app.db.queries import (
    create_database_engine,
    list_articles,
    upsert_wallet_principal,
)
from app.db.records import ArticleRecord
from app.db.schema import articles, publishers as publishers_table
from app.keystore import Keystore
from app.routes import articles as article_routes
from app.routes import auth, context, health, publishers, subscriptions
from app.state import ActivationCache, AppState
from app.tempo_keychain import Keychain, PeriodCharge

ARTICLE_SLUG = "ai-agent-payments"
CONTEXT_SLUG = "context-for-machines"
TX_HASH = "0xtx"
CURRENCY = "0x20c0000000000000000000000000000000000000"
NETWORK = "tempo"
PAID_HEADERS = {"Authorization": "paid"}
RECEIPT_PAYLOAD = {
    "status": "success",
    "timestamp": "2026-04-01T12:00:00+00:00",
    "reference": TX_HASH,
    "method": "tempo",
}
PUBLISHER_ID = UUID("11111111-1111-1111-1111-111111111111")
PUBLISHER_RECIPIENT = "0x52908400098527886E0F7030069857D2E4169EE7"
ARTICLE_ID = UUID("22222222-2222-2222-2222-222222222222")
CONTEXT_ID = UUID("33333333-3333-3333-3333-333333333333")
IDENTITY_ID = UUID("44444444-4444-4444-4444-444444444444")
PUBLISHER_B_ID = UUID("77777777-7777-7777-7777-777777777777")
PUBLISHER_B_RECIPIENT = "0xDE709f2102306220921060314715629080e2fB77"
ARTICLE_B_ID = UUID("88888888-8888-8888-8888-888888888888")
ARTICLE_B_SLUG = "publisher-b-article"


@dataclass(frozen=True)
class ChargeCall:
    """MPP charge invocation captured by tests."""

    authorization: Optional[str]
    amount: str
    memo: str
    recipient: Optional[str]


@dataclass(frozen=True)
class SuccessfulCharge:
    """Successful MPP charge result unpacked by the route."""

    credential: Credential
    receipt: Receipt

    def __iter__(self) -> Iterator[Credential | Receipt]:
        """Yield charge parts in the order returned by MPP."""
        yield self.credential
        yield self.receipt


MPP_SECRET_KEY = "test-secret-key"


class FakeMpp:
    """Fake MPP handler that returns a configured charge result."""

    def __init__(self, result: Challenge | SuccessfulCharge) -> None:
        self.realm = "agent-context"
        self.secret_key = MPP_SECRET_KEY
        self.result = result
        self.calls: list[ChargeCall] = []

    async def charge(
        self,
        authorization: Optional[str],
        amount: str,
        *,
        memo: str,
        recipient: Optional[str],
    ) -> Challenge | SuccessfulCharge:
        """Record a charge request and return the configured result."""
        self.calls.append(
            ChargeCall(
                authorization=authorization,
                amount=amount,
                memo=memo,
                recipient=recipient,
            )
        )
        return self.result


@dataclass
class FakeKeychain:
    """In-memory Keychain that records calls and returns canned outcomes."""

    verify_outcome: Optional[BaseException] = None
    charge_outcomes: list[PeriodCharge | BaseException] = field(
        default_factory=lambda: []
    )
    verify_calls: list[dict[str, object]] = field(default_factory=lambda: [])
    charge_calls: list[dict[str, object]] = field(default_factory=lambda: [])

    async def verify_authorize_key_tx(
        self,
        *,
        wallet_address: str,
        key_id: str,
        expected_monthly_price: Decimal,
        currency: str,
        expected_expiry: datetime,
        tx_hash: str,
    ) -> None:
        """Record verify call; raise the configured outcome if any."""
        self.verify_calls.append(
            {
                "wallet_address": wallet_address,
                "key_id": key_id,
                "expected_monthly_price": expected_monthly_price,
                "currency": currency,
                "expected_expiry": expected_expiry,
                "tx_hash": tx_hash,
            }
        )
        if isinstance(self.verify_outcome, BaseException):
            raise self.verify_outcome

    async def submit_period_charge(
        self,
        *,
        access_key_private_key: str,
        wallet_address: str,
        recipient: str,
        currency: str,
        monthly_price: Decimal,
        memo: bytes,
    ) -> PeriodCharge:
        """Record charge call; return / raise the next configured outcome."""
        self.charge_calls.append(
            {
                "access_key_private_key": access_key_private_key,
                "wallet_address": wallet_address,
                "recipient": recipient,
                "currency": currency,
                "monthly_price": monthly_price,
                "memo": memo,
            }
        )
        if not self.charge_outcomes:
            raise AssertionError("FakeKeychain has no remaining charge outcomes")
        outcome = self.charge_outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


@dataclass(frozen=True)
class RouteClient:
    """Test client and resources configured for route tests."""

    client: TestClient
    engine: Engine
    articles: dict[str, ArticleRecord]
    mpp: FakeMpp
    keystore: Keystore
    keychain: FakeKeychain
    activation_cache: ActivationCache


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


@pytest.fixture
def subscription_client(
    engine: Engine,
    article_catalog: dict[str, ArticleRecord],
    challenge: Challenge,
) -> RouteClient:
    """Return a route client wired with a configurable FakeKeychain."""
    return _route_client(engine, article_catalog, FakeMpp(challenge), FakeKeychain())


def create_challenge_nonce(client: RouteClient) -> str:
    """Issue a fresh WalletProof challenge nonce via /auth/challenge."""
    response = client.client.post("/auth/challenge")
    assert response.status_code == 200
    return cast(str, response.json()["challenge"])


def wallet_proof_header(nonce: str, account: object) -> dict[str, str]:
    """Build a WalletProof Authorization header for a signing account."""
    from eth_account.messages import encode_defunct

    message = encode_defunct(text=nonce)
    signed = cast(object, account).sign_message(message)  # type: ignore[attr-defined]
    signature = cast(bytes, signed.signature).hex()  # type: ignore[attr-defined]
    return {"Authorization": f"WalletProof {nonce}.{signature}"}


def subscription_count(engine: Engine) -> int:
    """Return the number of persisted subscription period rows."""
    with engine.connect() as connection:
        return cast(
            int,
            connection.execute(text("select count(*) from subscriptions")).scalar_one(),
        )


def authorization_count(engine: Engine, status: Optional[str] = None) -> int:
    """Return the number of subscription authorizations, optionally by status."""
    if status is None:
        sql = text("select count(*) from subscription_authorizations")
        params: dict[str, object] = {}
    else:
        sql = text("select count(*) from subscription_authorizations where status = :s")
        params = {"s": status}
    with engine.connect() as connection:
        return cast(int, connection.execute(sql, params).scalar_one())


def authorization_status(engine: Engine, authorization_id: UUID) -> str:
    """Return the persisted status for a given authorization id."""
    with engine.connect() as connection:
        return cast(
            str,
            connection.execute(
                text("select status from subscription_authorizations where id = :id"),
                {"id": authorization_id},
            ).scalar_one(),
        )


def purchase_count(engine: Engine) -> int:
    """Return the number of persisted one-time purchases."""
    with engine.connect() as connection:
        return cast(
            int,
            connection.execute(
                text("select count(*) from one_time_purchases")
            ).scalar_one(),
        )


def wallet_count(engine: Engine) -> int:
    """Return the number of persisted wallet principals."""
    with engine.connect() as connection:
        return cast(
            int,
            connection.execute(
                text("select count(*) from wallet_principals")
            ).scalar_one(),
        )


def _route_client(
    engine: Engine,
    article_catalog: dict[str, ArticleRecord],
    fake_mpp: FakeMpp,
    fake_keychain: Optional[FakeKeychain] = None,
) -> RouteClient:
    keystore = Keystore(Fernet.generate_key().decode())
    keychain = fake_keychain if fake_keychain is not None else FakeKeychain()
    activation_cache = ActivationCache()
    app = FastAPI()
    app.state.ctx = AppState(
        engine=engine,
        mpp=cast(Mpp, fake_mpp),
        pathusd_address=CURRENCY,
        tempo_network=NETWORK,
        keystore=keystore,
        keychain=cast(Keychain, keychain),
        activation_cache=activation_cache,
    )
    app.include_router(health.router)
    app.include_router(article_routes.router)
    app.include_router(context.router)
    app.include_router(auth.router)
    app.include_router(publishers.router)
    app.include_router(subscriptions.router)
    return RouteClient(
        client=TestClient(app),
        engine=engine,
        articles=article_catalog,
        mpp=fake_mpp,
        keystore=keystore,
        keychain=keychain,
        activation_cache=activation_cache,
    )


def _truncate_age10_tables(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                truncate table
                    subscription_renewal_attempts,
                    subscription_authorization_keys,
                    subscription_authorizations,
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


OWNER_ADDRESS = "0x52908400098527886e0f7030069857d2e4169ee7"


def _insert_article_catalog(engine: Engine) -> None:
    created_at = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
    upsert_wallet_principal(engine, OWNER_ADDRESS)
    with engine.begin() as connection:
        connection.execute(
            insert(publishers_table).values(
                id=PUBLISHER_ID,
                handle="agent-context-research",
                display_name="Agent Context Research",
                owner_address=OWNER_ADDRESS,
                description="Research publisher",
                status="active",
                recipient_address=PUBLISHER_RECIPIENT,
                default_article_price=Decimal("0.25"),
                default_subscription_price=Decimal("5.00"),
                created_at=created_at,
            )
        )
        connection.execute(
            insert(publishers_table).values(
                id=PUBLISHER_B_ID,
                handle="publisher-b",
                display_name="Publisher B",
                owner_address=OWNER_ADDRESS,
                description="Publisher B",
                status="active",
                recipient_address=PUBLISHER_B_RECIPIENT,
                default_article_price=Decimal("0.50"),
                default_subscription_price=Decimal("10.00"),
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
                    PUBLISHER_ID,
                ),
                _article_values(
                    CONTEXT_ID,
                    CONTEXT_SLUG,
                    "Context for Machines",
                    Decimal("1.25"),
                    created_at,
                    PUBLISHER_ID,
                ),
                _article_values(
                    IDENTITY_ID,
                    "decentralized-identity",
                    "Decentralized Identity",
                    Decimal("0.75"),
                    created_at,
                    PUBLISHER_ID,
                ),
                _article_values(
                    ARTICLE_B_ID,
                    ARTICLE_B_SLUG,
                    "Publisher B Article",
                    Decimal("0.50"),
                    created_at,
                    PUBLISHER_B_ID,
                ),
            ],
        )


def _article_values(
    article_id: UUID,
    slug: str,
    title: str,
    price: Decimal,
    created_at: datetime,
    publisher_id: UUID,
) -> dict[str, object]:
    return {
        "id": article_id,
        "publisher_id": publisher_id,
        "slug": slug,
        "title": title,
        "status": "published",
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

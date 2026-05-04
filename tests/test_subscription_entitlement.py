"""Tests for subscription-first entitlement on the paid context route."""
# pyright: reportArgumentType=false, reportIndexIssue=false

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from cryptography.fernet import Fernet
from eth_account import Account
from mpp import Receipt
from sqlalchemy.engine import Engine

from app.db.queries import (
    insert_authorization_with_key,
    insert_one_time_purchase,
    insert_subscription_period,
    upsert_wallet_principal,
)
from app.db.records import OneTimePurchase, SubscriptionPeriod
from app.keystore import Keystore
from app.models import ContextPackage
from conftest import (
    ARTICLE_B_SLUG,
    ARTICLE_ID,
    ARTICLE_SLUG,
    CURRENCY,
    NETWORK,
    PUBLISHER_B_ID,
    PUBLISHER_ID,
    PUBLISHER_RECIPIENT,
    RouteClient,
    create_challenge_nonce,
    wallet_proof_header,
)


def _seed_active_subscription_for(engine: Engine, wallet_address: str) -> str:
    """Insert an authorization + active period; return the period's tx hash."""
    keystore = Keystore(Fernet.generate_key().decode())
    upsert_wallet_principal(engine, wallet_address)
    insert_authorization_with_key(
        engine,
        wallet_address=wallet_address,
        publisher_id=PUBLISHER_ID,
        key_id="0xak-entitlement",
        expiry=datetime.now(UTC) + timedelta(days=365),
        authorize_tx_hash=f"0xauth-{wallet_address}",
        encrypted_key=keystore.encrypt(b"\x01" * 32),
    )
    period_start = datetime.now(UTC) - timedelta(days=1)
    period_end = period_start + timedelta(days=30)
    tx_hash = f"0xperiod-{wallet_address}"
    insert_subscription_period(
        engine,
        SubscriptionPeriod(
            id=uuid4(),
            wallet_address=wallet_address,
            publisher_id=PUBLISHER_ID,
            period_start=period_start,
            period_end=period_end,
            payment_reference=tx_hash,
            amount=Decimal("5.00"),
            currency=CURRENCY,
            network=NETWORK,
            receipt={
                "status": "success",
                "timestamp": period_start.isoformat(),
                "reference": tx_hash,
                "method": "tempo-access-key",
            },
        ),
    )
    return tx_hash


def test_active_subscriber_with_walletproof_gets_content_without_payment(
    challenge_client: RouteClient,
) -> None:
    account = Account.create()
    wallet_address = account.address.lower()
    tx_hash = _seed_active_subscription_for(challenge_client.engine, wallet_address)
    nonce = create_challenge_nonce(challenge_client)
    headers = wallet_proof_header(nonce, account)

    response = challenge_client.client.get(
        f"/articles/{ARTICLE_SLUG}/context", headers=headers
    )

    assert response.status_code == 200, response.text
    payload = ContextPackage.model_validate(response.json())
    assert payload.receipt["reference"] == tx_hash
    # Header is wire-compatible with the PPV path's Receipt.from_payment_receipt.
    parsed = Receipt.from_payment_receipt(response.headers["Payment-Receipt"])
    assert parsed.reference == tx_hash
    # The subscription path bypasses MPP entirely.
    assert challenge_client.mpp.calls == []


def test_walletproof_without_subscription_returns_402(
    challenge_client: RouteClient,
) -> None:
    account = Account.create()
    nonce = create_challenge_nonce(challenge_client)
    headers = wallet_proof_header(nonce, account)

    response = challenge_client.client.get(
        f"/articles/{ARTICLE_SLUG}/context", headers=headers
    )

    assert response.status_code == 402
    # Authorization header was dropped before MPP saw it (so MPP gets None).
    assert challenge_client.mpp.calls
    assert challenge_client.mpp.calls[0].authorization is None


def test_active_subscription_for_other_publisher_does_not_unlock(
    challenge_client: RouteClient,
) -> None:
    """Subscription to publisher A must not unlock publisher B's article."""
    account = Account.create()
    wallet_address = account.address.lower()
    # Seed a sub for publisher A then ask for publisher B's article.
    _seed_active_subscription_for(challenge_client.engine, wallet_address)
    nonce = create_challenge_nonce(challenge_client)
    headers = wallet_proof_header(nonce, account)

    response = challenge_client.client.get(
        f"/articles/{ARTICLE_B_SLUG}/context", headers=headers
    )

    assert response.status_code == 402
    # Sanity: the seeded sub is for publisher A, not B.
    assert PUBLISHER_ID != PUBLISHER_B_ID


def test_payment_auth_path_still_works_for_unsubscribed_wallet(
    paid_client: RouteClient,
) -> None:
    """A wallet without a subscription can still pay PPV via the existing flow."""
    response = paid_client.client.get(
        f"/articles/{ARTICLE_SLUG}/context",
        headers={"Authorization": "paid"},
    )

    assert response.status_code == 200
    payload = ContextPackage.model_validate(response.json())
    # The receipt comes from the PPV (MPP) path, not a subscription row.
    assert payload.receipt["method"] == "tempo"


def _seed_one_time_purchase(
    engine: Engine, wallet_address: str, article_id: UUID, *, tx_hash: str
) -> str:
    """Insert a one_time_purchases row directly; returns the tx hash."""
    upsert_wallet_principal(engine, wallet_address)
    insert_one_time_purchase(
        engine,
        OneTimePurchase(
            article_slug=ARTICLE_SLUG,
            wallet_address=wallet_address,
            payment_reference=tx_hash,
            amount=Decimal("0.25"),
            currency=CURRENCY,
            network=NETWORK,
            recipient_wallet=PUBLISHER_RECIPIENT.lower(),
            receipt={
                "status": "success",
                "timestamp": "2026-04-01T12:00:00+00:00",
                "reference": tx_hash,
                "method": "tempo",
            },
        ),
        article_id,
    )
    return tx_hash


def test_prior_purchase_serves_article_without_charging(
    challenge_client: RouteClient,
) -> None:
    """Once paid, future reads of the same article succeed via WalletProof only."""
    account = Account.create()
    wallet_address = account.address.lower()
    tx_hash = _seed_one_time_purchase(
        challenge_client.engine,
        wallet_address,
        ARTICLE_ID,
        tx_hash="0xprior-purchase",
    )
    nonce = create_challenge_nonce(challenge_client)
    headers = wallet_proof_header(nonce, account)

    response = challenge_client.client.get(
        f"/articles/{ARTICLE_SLUG}/context", headers=headers
    )

    assert response.status_code == 200, response.text
    payload = ContextPackage.model_validate(response.json())
    assert payload.receipt["reference"] == tx_hash
    parsed = Receipt.from_payment_receipt(response.headers["Payment-Receipt"])
    assert parsed.reference == tx_hash
    # Persistent-PPV branch must bypass MPP entirely.
    assert challenge_client.mpp.calls == []


def test_prior_purchase_does_not_unlock_other_articles(
    challenge_client: RouteClient,
) -> None:
    """A purchase for article A must not entitle the wallet to article B."""
    account = Account.create()
    wallet_address = account.address.lower()
    _seed_one_time_purchase(
        challenge_client.engine,
        wallet_address,
        ARTICLE_ID,
        tx_hash="0xprior-A",
    )
    nonce = create_challenge_nonce(challenge_client)
    headers = wallet_proof_header(nonce, account)

    response = challenge_client.client.get(
        f"/articles/{ARTICLE_B_SLUG}/context", headers=headers
    )

    assert response.status_code == 402
    # WalletProof was identified-but-not-entitled, so MPP saw no auth header.
    assert challenge_client.mpp.calls
    assert challenge_client.mpp.calls[0].authorization is None

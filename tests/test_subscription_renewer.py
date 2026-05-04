"""Tests for the daily subscription renewer (scripts/renew_subscriptions.py)."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.engine import Engine

from sqlalchemy import text

from app.config import Settings
from app.db.queries import (
    insert_authorization_with_key,
    insert_subscription_period,
    select_due_renewals,
)
from app.db.records import SubscriptionPeriod
from app.keystore import Keystore
from app.tempo_keychain import PeriodCharge, PeriodChargeError
from conftest import (
    CURRENCY,
    NETWORK,
    PUBLISHER_ID,
    FakeKeychain,
    authorization_status,
    subscription_count,
)
from scripts.renew_subscriptions import renew_due_subscriptions

PERIOD_SECONDS = 30 * 24 * 60 * 60


def _settings(monkeypatch: pytest.MonkeyPatch, fernet_key: str) -> Settings:
    """Build a Settings instance using current env plus the test fernet key."""
    monkeypatch.setenv("SUBSCRIPTION_KEYSTORE_KEY", fernet_key)
    monkeypatch.setenv("ENVIRONMENT", os.environ.get("ENVIRONMENT", "test"))
    monkeypatch.setenv("TEMPO_NETWORK", os.environ.get("TEMPO_NETWORK", "moderato"))
    monkeypatch.setenv(
        "MAINNET_CONFIRMATION",
        os.environ.get("MAINNET_CONFIRMATION", "false"),
    )
    monkeypatch.setenv("MPP_REALM", os.environ.get("MPP_REALM", "agent-context"))
    monkeypatch.setenv(
        "MPP_SECRET_KEY", os.environ.get("MPP_SECRET_KEY", "test-secret-key")
    )
    monkeypatch.setenv(
        "PATHUSD_ADDRESS",
        os.environ.get("PATHUSD_ADDRESS", "0x20c0000000000000000000000000000000000000"),
    )
    return Settings()


def _seed_active_subscription(
    engine: Engine,
    keystore: Keystore,
    *,
    wallet_address: str,
    period_start: datetime,
    last_period_end: datetime,
) -> tuple[str, str]:
    """Insert an active authorization plus its initial period row."""
    encrypted = keystore.encrypt(b"\xab" * 32)
    authorization = insert_authorization_with_key(
        engine,
        wallet_address=wallet_address,
        publisher_id=PUBLISHER_ID,
        key_id="0xak",
        expiry=datetime.now(UTC) + timedelta(days=365),
        authorize_tx_hash=f"0xauth-{wallet_address}",
        encrypted_key=encrypted,
    )
    insert_subscription_period(
        engine,
        SubscriptionPeriod(
            id=uuid4(),
            wallet_address=wallet_address,
            publisher_id=PUBLISHER_ID,
            period_start=period_start,
            period_end=last_period_end,
            payment_reference=f"0xseed-{wallet_address}",
            amount=Decimal("5.00"),
            currency=CURRENCY,
            network=NETWORK,
            receipt={
                "status": "success",
                "timestamp": period_start.isoformat(),
                "reference": f"0xseed-{wallet_address}",
                "method": "tempo-access-key",
            },
        ),
    )
    return str(authorization.id), authorization.key_id


def test_renewer_charges_due_subscription_and_inserts_new_period(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    fernet_key = Fernet.generate_key().decode()
    settings = _settings(monkeypatch, fernet_key)
    keystore = Keystore(fernet_key)
    wallet = "0xrenew1"
    last_end = datetime.now(UTC) - timedelta(minutes=5)
    auth_id, _ = _seed_active_subscription(
        engine,
        keystore,
        wallet_address=wallet,
        period_start=last_end - timedelta(seconds=PERIOD_SECONDS),
        last_period_end=last_end,
    )
    keychain = FakeKeychain()
    keychain.charge_outcomes.append(
        PeriodCharge(
            payment_reference="0xperiod2",
            block_number=99,
            payer_address=wallet,
        )
    )

    summary = asyncio.run(renew_due_subscriptions(settings, keystore, keychain))

    assert summary.succeeded == [auth_id]
    assert summary.retried == []
    assert summary.failed == []
    assert subscription_count(engine) == 2


def test_renewer_records_attempt_on_transient_failure(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    fernet_key = Fernet.generate_key().decode()
    settings = _settings(monkeypatch, fernet_key)
    keystore = Keystore(fernet_key)
    wallet = "0xrenew2"
    last_end = datetime.now(UTC) - timedelta(minutes=5)
    auth_id, _ = _seed_active_subscription(
        engine,
        keystore,
        wallet_address=wallet,
        period_start=last_end - timedelta(seconds=PERIOD_SECONDS),
        last_period_end=last_end,
    )
    keychain = FakeKeychain()
    keychain.charge_outcomes.append(PeriodChargeError("rpc blip"))

    summary = asyncio.run(renew_due_subscriptions(settings, keystore, keychain))

    assert summary.retried == [auth_id]
    assert summary.failed == []
    assert authorization_status(engine, UUID(auth_id)) == "active"
    assert subscription_count(engine) == 1


def test_renewer_marks_failed_after_three_attempts(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    fernet_key = Fernet.generate_key().decode()
    settings = _settings(monkeypatch, fernet_key)
    keystore = Keystore(fernet_key)
    wallet = "0xrenew3"
    last_end = datetime.now(UTC) - timedelta(minutes=5)
    auth_id, _ = _seed_active_subscription(
        engine,
        keystore,
        wallet_address=wallet,
        period_start=last_end - timedelta(seconds=PERIOD_SECONDS),
        last_period_end=last_end,
    )
    keychain = FakeKeychain()
    # Pre-load 3 failures; renewer pops one per pass.
    keychain.charge_outcomes.extend(
        [
            PeriodChargeError("rpc1"),
            PeriodChargeError("rpc2"),
            PeriodChargeError("rpc3"),
        ]
    )
    # Bypass the 8h retry-gap by clearing attempts inline. Simulate three
    # passes by re-running `renew_due_subscriptions` and resetting
    # `last_attempt_at` between runs to satisfy the gap predicate.
    for _ in range(3):
        # Force the attempt-gap predicate to consider this row eligible by
        # rewinding the last_attempt_at timestamp by 9 hours.
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    update subscription_renewal_attempts
                       set last_attempt_at = last_attempt_at - interval '9 hours'
                     where authorization_id = :id
                    """
                ),
                {"id": auth_id},
            )
        # Re-check there is at least one due row before each pass.
        due = select_due_renewals(
            engine,
            datetime.now(UTC),
            expiry_buffer_seconds=24 * 60 * 60,
            retry_gap_seconds=8 * 60 * 60,
            max_attempts=3,
        )
        if not due:
            break
        asyncio.run(renew_due_subscriptions(settings, keystore, keychain))

    assert authorization_status(engine, UUID(auth_id)) == ("renewal_failed")


def test_renewer_skips_cancelled_authorizations(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    fernet_key = Fernet.generate_key().decode()
    settings = _settings(monkeypatch, fernet_key)
    keystore = Keystore(fernet_key)
    wallet = "0xrenew4"
    last_end = datetime.now(UTC) - timedelta(minutes=5)
    auth_id, _ = _seed_active_subscription(
        engine,
        keystore,
        wallet_address=wallet,
        period_start=last_end - timedelta(seconds=PERIOD_SECONDS),
        last_period_end=last_end,
    )

    with engine.begin() as connection:
        connection.execute(
            text(
                "update subscription_authorizations set status='cancelled'"
                " where id = :id"
            ),
            {"id": auth_id},
        )
    keychain = FakeKeychain()  # no charge outcomes — should never be called

    summary = asyncio.run(renew_due_subscriptions(settings, keystore, keychain))

    assert summary.succeeded == []
    assert summary.retried == []
    assert summary.failed == []
    assert keychain.charge_calls == []

"""End-to-end integration test for the AGE-16 subscription + PPV lifecycle.

Walks one wallet through every transition that the entitlement system can
observe, against a real Postgres test DB. Periods are not waited out;
expiration is simulated by rewriting ``subscriptions.period_end`` directly
so the whole journey runs in seconds while still exercising the actual
state transitions a 30-day cycle would produce.
"""
# pyright: reportArgumentType=false, reportIndexIssue=false

import asyncio
import os
from datetime import UTC, datetime
from typing import Any

import pytest
from cryptography.fernet import Fernet
from eth_account import Account
from mpp import ChallengeEcho, Credential, Receipt
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.config import Settings
from app.tempo_keychain import PeriodCharge
from conftest import (
    ARTICLE_B_SLUG,
    ARTICLE_SLUG,
    PUBLISHER_RECIPIENT,
    RouteClient,
    SuccessfulCharge,
    authorization_count,
    create_challenge_nonce,
    subscription_count,
    wallet_proof_header,
)
from scripts.renew_subscriptions import renew_due_subscriptions

PUBLISHER_HANDLE = "agent-context-research"
SECOND_PUBLISHER_ARTICLE = ARTICLE_B_SLUG
SAME_PUBLISHER_SECOND_ARTICLE = "context-for-machines"


def _read(client: RouteClient, account: object, slug: str) -> Any:
    """Fetch a fresh nonce, sign a WalletProof, GET the context endpoint."""
    nonce = create_challenge_nonce(client)
    headers = wallet_proof_header(nonce, account)
    return client.client.get(f"/articles/{slug}/context", headers=headers)


def _build_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Materialize Settings from env, defaulting any vars pytest didn't set."""
    monkeypatch.setenv(
        "SUBSCRIPTION_KEYSTORE_KEY",
        os.environ.get("SUBSCRIPTION_KEYSTORE_KEY", Fernet.generate_key().decode()),
    )
    monkeypatch.setenv("ENVIRONMENT", os.environ.get("ENVIRONMENT", "test"))
    monkeypatch.setenv("TEMPO_NETWORK", os.environ.get("TEMPO_NETWORK", "moderato"))
    monkeypatch.setenv(
        "MAINNET_CONFIRMATION",
        os.environ.get("MAINNET_CONFIRMATION", "false"),
    )
    monkeypatch.setenv("MPP_REALM", os.environ.get("MPP_REALM", "agent-context"))
    monkeypatch.setenv(
        "MPP_SECRET_KEY",
        os.environ.get("MPP_SECRET_KEY", "test-secret-key"),
    )
    monkeypatch.setenv(
        "PATHUSD_ADDRESS",
        os.environ.get("PATHUSD_ADDRESS", "0x20c0000000000000000000000000000000000000"),
    )
    return Settings()


def _expire_all_periods(engine: Engine) -> None:
    """Fast-forward time: shrink any active period so period_end is in the past.

    Sets period_end = period_start + 1ms on rows that haven't yet expired,
    which keeps the CHECK constraint (period_end > period_start) satisfied
    while moving the row out of the "now is inside [period_start, period_end)"
    entitlement window.
    """
    with engine.begin() as connection:
        connection.execute(
            text(
                "update subscriptions "
                "set period_end = period_start + interval '1 millisecond' "
                "where period_end > now()"
            )
        )


def test_subscription_and_ppv_lifecycle_end_to_end(
    subscription_client: RouteClient,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Subscribe → use → renew → use → cancel → use → expire → PPV → re-read."""
    subscriber = Account.create()
    subscriber_address = subscriber.address.lower()

    # ── Phase 1: anonymous read returns a PPV 402 challenge ─────────
    response = subscription_client.client.get(f"/articles/{ARTICLE_SLUG}/context")
    assert response.status_code == 402
    assert response.headers["WWW-Authenticate"].startswith("Payment ")

    # ── Phase 2: subscribe (begin → activate, DB rows persisted) ────
    nonce = create_challenge_nonce(subscription_client)
    begin = subscription_client.client.post(
        f"/api/subscriptions/{PUBLISHER_HANDLE}",
        headers=wallet_proof_header(nonce, subscriber),
    )
    assert begin.status_code == 200, begin.text
    mandate = begin.json()
    assert mandate["recipient"] == PUBLISHER_RECIPIENT
    assert int(mandate["period_seconds"]) == 30 * 24 * 60 * 60

    subscription_client.keychain.charge_outcomes.append(
        PeriodCharge(
            payment_reference="0xperiod-1",
            block_number=1,
            payer_address=subscriber_address,
        )
    )
    activate_nonce = create_challenge_nonce(subscription_client)
    activate = subscription_client.client.post(
        f"/api/subscriptions/{PUBLISHER_HANDLE}/activate",
        json={
            "session_token": mandate["session_token"],
            "authorize_tx_hash": "0xauthorize",
        },
        headers=wallet_proof_header(activate_nonce, subscriber),
    )
    assert activate.status_code == 201, activate.text
    assert activate.json()["status"] == "active"
    assert activate.json()["current_period"]["payment_reference"] == "0xperiod-1"
    assert authorization_count(engine, status="active") == 1
    assert subscription_count(engine) == 1

    # ── Phase 3: subscriber reads via WalletProof, no MPP charge ────
    pre_calls = len(subscription_client.mpp.calls)
    response = _read(subscription_client, subscriber, ARTICLE_SLUG)
    assert response.status_code == 200
    parsed = Receipt.from_payment_receipt(response.headers["Payment-Receipt"])
    assert parsed.reference == "0xperiod-1"
    assert len(subscription_client.mpp.calls) == pre_calls

    # ── Phase 4: same publisher's other article also unlocked ───────
    response = _read(subscription_client, subscriber, SAME_PUBLISHER_SECOND_ARTICLE)
    assert response.status_code == 200

    # ── Phase 5: different publisher → 402 (per-publisher boundary) ─
    response = _read(subscription_client, subscriber, SECOND_PUBLISHER_ARTICLE)
    assert response.status_code == 402

    # ── Phase 6: fast-forward 30 days (period 1 expires) ────────────
    _expire_all_periods(engine)

    # ── Phase 7: post-expiry read → 402 (no current period) ─────────
    response = _read(subscription_client, subscriber, ARTICLE_SLUG)
    assert response.status_code == 402

    # ── Phase 8: renewer charges period 2, inserts new row ──────────
    settings = _build_settings(monkeypatch)
    subscription_client.keychain.charge_outcomes.append(
        PeriodCharge(
            payment_reference="0xperiod-2",
            block_number=2,
            payer_address=subscriber_address,
        )
    )
    summary = asyncio.run(
        renew_due_subscriptions(
            settings,
            subscription_client.keystore,
            subscription_client.keychain,
        )
    )
    assert len(summary.succeeded) == 1
    assert len(summary.failed) == 0
    assert subscription_count(engine) == 2  # period 1 + period 2

    # ── Phase 9: renewed period serves with NEW receipt reference ───
    response = _read(subscription_client, subscriber, ARTICLE_SLUG)
    assert response.status_code == 200
    parsed = Receipt.from_payment_receipt(response.headers["Payment-Receipt"])
    assert parsed.reference == "0xperiod-2"  # the renewal, not period-1

    # ── Phase 10: cancel — current (period 2) stays valid ───────────
    cancel_nonce = create_challenge_nonce(subscription_client)
    cancel = subscription_client.client.delete(
        f"/api/subscriptions/{PUBLISHER_HANDLE}",
        headers=wallet_proof_header(cancel_nonce, subscriber),
    )
    assert cancel.status_code == 200
    cancel_body = cancel.json()
    assert cancel_body["status"] == "cancelled"
    assert cancel_body["revoke_call"]["data"].startswith("0x")
    assert authorization_count(engine, status="cancelled") == 1

    response = _read(subscription_client, subscriber, ARTICLE_SLUG)
    assert response.status_code == 200  # period 2 not yet expired

    # ── Phase 11: fast-forward past period 2 → 402 (no entitlement) ─
    _expire_all_periods(engine)
    response = _read(subscription_client, subscriber, ARTICLE_SLUG)
    assert response.status_code == 402

    # Renewer ignores cancelled authorizations even when "due."
    pre_charge_count = len(subscription_client.keychain.charge_calls)
    summary = asyncio.run(
        renew_due_subscriptions(
            settings,
            subscription_client.keystore,
            subscription_client.keychain,
        )
    )
    assert summary.succeeded == []
    assert summary.retried == []
    assert summary.failed == []
    assert len(subscription_client.keychain.charge_calls) == pre_charge_count

    # ── Phase 12: pay one-time PPV; switch FakeMpp to success mode ──
    subscription_client.mpp.result = SuccessfulCharge(
        credential=Credential(
            challenge=ChallengeEcho(
                id="e2e-charge",
                realm="agent-context",
                method="tempo",
                intent="charge",
                request="e30",
            ),
            payload={"authorization": "paid"},
            source=f"tempo:{subscriber_address}",
        ),
        receipt=Receipt(
            status="success",
            timestamp=datetime.now(UTC),
            reference="0xppv-tx",
            method="tempo",
        ),
    )
    response = subscription_client.client.get(
        f"/articles/{ARTICLE_SLUG}/context",
        headers={"Authorization": "paid"},
    )
    assert response.status_code == 200
    first_receipt = Receipt.from_payment_receipt(response.headers["Payment-Receipt"])
    assert first_receipt.reference == "0xppv-tx"
    with engine.connect() as connection:
        ppv_count = connection.execute(
            text("select count(*) from one_time_purchases where wallet_address = :w"),
            {"w": subscriber_address},
        ).scalar_one()
    assert ppv_count == 1

    # ── Phase 13: re-read with WalletProof — persistent PPV bypasses MPP ─
    pre_mpp_calls = len(subscription_client.mpp.calls)
    response = _read(subscription_client, subscriber, ARTICLE_SLUG)
    assert response.status_code == 200
    reread_receipt = Receipt.from_payment_receipt(response.headers["Payment-Receipt"])
    assert reread_receipt.reference == first_receipt.reference
    # The whole point of the recent fix: zero new MPP calls.
    assert len(subscription_client.mpp.calls) == pre_mpp_calls

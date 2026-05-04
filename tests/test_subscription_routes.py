"""End-to-end tests for the per-publisher subscription routes."""
# pyright: reportArgumentType=false, reportIndexIssue=false

from datetime import datetime
from decimal import Decimal
from typing import Any

from eth_account import Account

from app.tempo_keychain import (
    KeychainVerificationError,
    PeriodCharge,
    PeriodChargeError,
)
from conftest import (
    RouteClient,
    authorization_count,
    create_challenge_nonce,
    subscription_count,
    wallet_proof_header,
)

PUBLISHER_HANDLE = "agent-context-research"
ACTIVATE_PATH = f"/api/subscriptions/{PUBLISHER_HANDLE}/activate"
BEGIN_PATH = f"/api/subscriptions/{PUBLISHER_HANDLE}"


def _begin_subscription(
    client: RouteClient, account: object
) -> tuple[dict[str, Any], dict[str, str]]:
    """POST /api/subscriptions/{handle} as a fresh wallet, return mandate."""
    nonce = create_challenge_nonce(client)
    headers = wallet_proof_header(nonce, account)
    response = client.client.post(BEGIN_PATH, headers=headers)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body, headers


def test_begin_returns_mandate_and_caches_session(
    subscription_client: RouteClient,
) -> None:
    account = Account.create()

    mandate, _ = _begin_subscription(subscription_client, account)

    assert mandate["recipient"]
    assert mandate["currency"]
    assert mandate["period_seconds"] == 30 * 24 * 60 * 60
    assert mandate["session_token"]
    assert mandate["authorize_call"]["to"]
    assert mandate["authorize_call"]["data"].startswith("0x")


def test_begin_then_activate_persists_authorization_and_period(
    subscription_client: RouteClient,
) -> None:
    account = Account.create()
    subscription_client.keychain.charge_outcomes.append(
        PeriodCharge(
            payment_reference="0xperiod1",
            block_number=42,
            payer_address=account.address.lower(),
        )
    )

    mandate, _ = _begin_subscription(subscription_client, account)
    nonce = create_challenge_nonce(subscription_client)
    headers = wallet_proof_header(nonce, account)
    activate = subscription_client.client.post(
        ACTIVATE_PATH,
        json={
            "session_token": mandate["session_token"],
            "authorize_tx_hash": "0xauthorize",
        },
        headers=headers,
    )

    assert activate.status_code == 201, activate.text
    body = activate.json()
    assert body["status"] == "active"
    assert body["current_period"]["payment_reference"] == "0xperiod1"
    assert authorization_count(subscription_client.engine, status="active") == 1
    assert subscription_count(subscription_client.engine) == 1
    # The keychain was asked to verify and to charge once.
    assert len(subscription_client.keychain.verify_calls) == 1
    assert len(subscription_client.keychain.charge_calls) == 1
    charge_call = subscription_client.keychain.charge_calls[0]
    assert charge_call["wallet_address"] == account.address.lower()
    assert isinstance(charge_call["memo"], (bytes, bytearray))
    assert len(charge_call["memo"]) == 32


def test_activate_with_expired_session_token_returns_400(
    subscription_client: RouteClient,
) -> None:
    account = Account.create()

    mandate, _ = _begin_subscription(subscription_client, account)
    # Manually expire by clearing the entry.
    subscription_client.activation_cache.consume(mandate["session_token"])

    nonce = create_challenge_nonce(subscription_client)
    headers = wallet_proof_header(nonce, account)
    activate = subscription_client.client.post(
        ACTIVATE_PATH,
        json={
            "session_token": mandate["session_token"],
            "authorize_tx_hash": "0xauthorize",
        },
        headers=headers,
    )

    assert activate.status_code == 400
    assert authorization_count(subscription_client.engine) == 0


def test_activate_with_session_for_other_wallet_returns_400(
    subscription_client: RouteClient,
) -> None:
    payer = Account.create()
    attacker = Account.create()
    subscription_client.keychain.charge_outcomes.append(
        PeriodCharge(
            payment_reference="0xperiod1",
            block_number=1,
            payer_address=payer.address.lower(),
        )
    )

    mandate, _ = _begin_subscription(subscription_client, payer)
    nonce = create_challenge_nonce(subscription_client)
    headers = wallet_proof_header(nonce, attacker)
    activate = subscription_client.client.post(
        ACTIVATE_PATH,
        json={
            "session_token": mandate["session_token"],
            "authorize_tx_hash": "0xauthorize",
        },
        headers=headers,
    )

    assert activate.status_code == 400
    assert authorization_count(subscription_client.engine) == 0


def test_activate_with_failing_verify_returns_400_no_persistence(
    subscription_client: RouteClient,
) -> None:
    account = Account.create()
    subscription_client.keychain.verify_outcome = KeychainVerificationError(
        "expiry mismatch"
    )

    mandate, _ = _begin_subscription(subscription_client, account)
    nonce = create_challenge_nonce(subscription_client)
    headers = wallet_proof_header(nonce, account)
    activate = subscription_client.client.post(
        ACTIVATE_PATH,
        json={
            "session_token": mandate["session_token"],
            "authorize_tx_hash": "0xauthorize",
        },
        headers=headers,
    )

    assert activate.status_code == 400
    assert authorization_count(subscription_client.engine) == 0
    assert subscription_count(subscription_client.engine) == 0


def test_activate_charge_failure_persists_nothing(
    subscription_client: RouteClient,
) -> None:
    """Plan contract: charge before persistence; failure leaves no DB rows."""
    account = Account.create()
    subscription_client.keychain.charge_outcomes.append(PeriodChargeError("rpc down"))

    mandate, _ = _begin_subscription(subscription_client, account)
    nonce = create_challenge_nonce(subscription_client)
    headers = wallet_proof_header(nonce, account)
    activate = subscription_client.client.post(
        ACTIVATE_PATH,
        json={
            "session_token": mandate["session_token"],
            "authorize_tx_hash": "0xauthorize",
        },
        headers=headers,
    )

    assert activate.status_code == 502
    assert subscription_count(subscription_client.engine) == 0
    assert authorization_count(subscription_client.engine) == 0


def test_double_subscribe_returns_409(
    subscription_client: RouteClient,
) -> None:
    account = Account.create()
    subscription_client.keychain.charge_outcomes.append(
        PeriodCharge(
            payment_reference="0xperiod1",
            block_number=1,
            payer_address=account.address.lower(),
        )
    )

    mandate, _ = _begin_subscription(subscription_client, account)
    nonce = create_challenge_nonce(subscription_client)
    headers = wallet_proof_header(nonce, account)
    first = subscription_client.client.post(
        ACTIVATE_PATH,
        json={
            "session_token": mandate["session_token"],
            "authorize_tx_hash": "0xauthorize",
        },
        headers=headers,
    )
    assert first.status_code == 201

    nonce_second = create_challenge_nonce(subscription_client)
    headers_second = wallet_proof_header(nonce_second, account)
    second = subscription_client.client.post(
        BEGIN_PATH,
        headers=headers_second,
    )

    assert second.status_code == 409


def test_cancel_marks_authorization_cancelled_and_returns_revoke_call(
    subscription_client: RouteClient,
) -> None:
    account = Account.create()
    subscription_client.keychain.charge_outcomes.append(
        PeriodCharge(
            payment_reference="0xperiod1",
            block_number=1,
            payer_address=account.address.lower(),
        )
    )
    mandate, _ = _begin_subscription(subscription_client, account)
    nonce = create_challenge_nonce(subscription_client)
    headers = wallet_proof_header(nonce, account)
    subscription_client.client.post(
        ACTIVATE_PATH,
        json={
            "session_token": mandate["session_token"],
            "authorize_tx_hash": "0xauthorize",
        },
        headers=headers,
    )

    cancel_nonce = create_challenge_nonce(subscription_client)
    cancel_headers = wallet_proof_header(cancel_nonce, account)
    cancel = subscription_client.client.delete(BEGIN_PATH, headers=cancel_headers)

    assert cancel.status_code == 200
    body = cancel.json()
    assert body["status"] == "cancelled"
    assert body["revoke_call"]["data"].startswith("0x")
    # Current period is preserved until period_end.
    assert body["current_period"] is not None
    assert authorization_count(subscription_client.engine, status="cancelled") == 1


def test_get_subscription_returns_status(
    subscription_client: RouteClient,
) -> None:
    account = Account.create()
    subscription_client.keychain.charge_outcomes.append(
        PeriodCharge(
            payment_reference="0xperiod1",
            block_number=1,
            payer_address=account.address.lower(),
        )
    )
    mandate, _ = _begin_subscription(subscription_client, account)
    nonce = create_challenge_nonce(subscription_client)
    headers = wallet_proof_header(nonce, account)
    subscription_client.client.post(
        ACTIVATE_PATH,
        json={
            "session_token": mandate["session_token"],
            "authorize_tx_hash": "0xauthorize",
        },
        headers=headers,
    )

    get_nonce = create_challenge_nonce(subscription_client)
    get_headers = wallet_proof_header(get_nonce, account)
    response = subscription_client.client.get(BEGIN_PATH, headers=get_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "active"
    assert body["current_period"]["payment_reference"] == "0xperiod1"
    # Make sure period_end is well past period_start by ~30 days.
    start = datetime.fromisoformat(body["current_period"]["period_start"])
    end = datetime.fromisoformat(body["current_period"]["period_end"])
    assert (end - start).total_seconds() == 30 * 24 * 60 * 60
    # Sanity: the subscription_price is publisher's default.
    assert (
        Decimal(mandate["monthly_price"])
        == subscription_client.keychain.charge_calls[0]["monthly_price"]
    )


def test_begin_unknown_publisher_returns_404(
    subscription_client: RouteClient,
) -> None:
    account = Account.create()
    nonce = create_challenge_nonce(subscription_client)
    headers = wallet_proof_header(nonce, account)

    response = subscription_client.client.post(
        "/api/subscriptions/no-such-publisher", headers=headers
    )

    assert response.status_code == 404


def test_get_without_subscription_returns_404(
    subscription_client: RouteClient,
) -> None:
    account = Account.create()
    nonce = create_challenge_nonce(subscription_client)
    headers = wallet_proof_header(nonce, account)

    response = subscription_client.client.get(BEGIN_PATH, headers=headers)

    assert response.status_code == 404

"""Tests for publisher CRUD endpoints."""

from decimal import Decimal

from eth_account import Account
from eth_account.messages import encode_defunct
from eth_account.signers.local import LocalAccount
from sqlalchemy import text, update
from sqlalchemy.engine import Engine

from app.db.queries import upsert_wallet_principal
from app.db.schema import publishers
from conftest import (
    ARTICLE_SLUG,
    PAID_HEADERS,
    PUBLISHER_ID,
    RouteClient,
)


def _create_challenge(client: RouteClient) -> str:
    response = client.client.post("/auth/challenge")
    assert response.status_code == 200
    return response.json()["challenge"]


def _wallet_proof_header(nonce: str, account: LocalAccount) -> dict[str, str]:
    message = encode_defunct(text=nonce)
    signed = account.sign_message(message)
    return {"Authorization": f"WalletProof {nonce}.{signed.signature.hex()}"}


def _auth_headers(client: RouteClient, account: LocalAccount) -> dict[str, str]:
    nonce = _create_challenge(client)
    return _wallet_proof_header(nonce, account)


def test_create_publisher_success(paid_client: RouteClient) -> None:
    account = Account.create()
    headers = _auth_headers(paid_client, account)

    response = paid_client.client.post(
        "/publishers",
        json={
            "handle": "new-pub",
            "display_name": "New Publisher",
            "description": "A new publisher",
            "recipient_address": account.address,
            "default_article_price": "0.50",
            "default_subscription_price": "10.00",
        },
        headers=headers,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["handle"] == "new-pub"
    assert data["display_name"] == "New Publisher"
    assert data["description"] == "A new publisher"
    assert data["owner_address"] == account.address.lower()
    assert data["status"] == "active"
    assert data["default_article_price"] == "0.50"
    assert data["default_subscription_price"] == "10.00"


def test_create_publisher_duplicate_handle_returns_409(
    paid_client: RouteClient,
) -> None:
    account = Account.create()
    headers = _auth_headers(paid_client, account)

    response = paid_client.client.post(
        "/publishers",
        json={
            "handle": "agent-context-research",
            "display_name": "Duplicate",
            "description": "Dup",
            "recipient_address": account.address,
            "default_article_price": "1.00",
            "default_subscription_price": "5.00",
        },
        headers=headers,
    )

    assert response.status_code == 409


def test_get_publisher_success(paid_client: RouteClient) -> None:
    response = paid_client.client.get("/publishers/agent-context-research")

    assert response.status_code == 200
    data = response.json()
    assert data["handle"] == "agent-context-research"
    assert data["display_name"] == "Agent Context Research"
    assert data["status"] == "active"


def test_get_publisher_not_found_returns_404(paid_client: RouteClient) -> None:
    response = paid_client.client.get("/publishers/nonexistent")

    assert response.status_code == 404


def test_patch_publisher_owner_success(paid_client: RouteClient) -> None:
    account = Account.create()
    _insert_test_publisher(paid_client.engine, account, "patch-pub", account.address)
    headers = _auth_headers(paid_client, account)

    response = paid_client.client.patch(
        "/publishers/patch-pub",
        json={
            "display_name": "Patched Name",
            "description": "Updated desc",
            "status": "disabled",
            "default_article_price": "2.00",
            "default_subscription_price": "20.00",
        },
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["display_name"] == "Patched Name"
    assert data["description"] == "Updated desc"
    assert data["status"] == "disabled"
    assert data["default_article_price"] == "2.00"
    assert data["default_subscription_price"] == "20.00"


def test_patch_publisher_unauthorized_returns_403(
    paid_client: RouteClient,
) -> None:
    account = Account.create()
    headers = _auth_headers(paid_client, account)

    response = paid_client.client.patch(
        "/publishers/agent-context-research",
        json={"display_name": "Hijacked"},
        headers=headers,
    )

    assert response.status_code == 403


def test_patch_publisher_not_found_returns_404(
    paid_client: RouteClient,
) -> None:
    account = Account.create()
    headers = _auth_headers(paid_client, account)

    response = paid_client.client.patch(
        "/publishers/no-such-publisher",
        json={"display_name": "Ghost"},
        headers=headers,
    )

    assert response.status_code == 404


def test_disabled_publisher_blocks_context_returns_403(
    paid_client: RouteClient,
) -> None:
    with paid_client.engine.begin() as connection:
        connection.execute(
            update(publishers)
            .where(publishers.c.id == PUBLISHER_ID)
            .values(status="disabled")
        )

    response = paid_client.client.get(
        f"/articles/{ARTICLE_SLUG}/context",
        headers=PAID_HEADERS,
    )

    assert response.status_code == 403
    assert paid_client.mpp.calls == []


def _insert_test_publisher(
    engine: Engine,
    account: LocalAccount,
    handle: str,
    recipient_address: str,
) -> None:
    """Insert a test publisher owned by the given account."""
    upsert_wallet_principal(engine, account.address.lower())
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO publishers
                    (id, handle, display_name, owner_address, description,
                     status, recipient_address, default_article_price,
                     default_subscription_price, created_at)
                VALUES
                    (gen_random_uuid(), :handle, :display_name, :owner_address,
                     :description, 'active', :recipient_address, :article_price,
                     :subscription_price, now())
                ON CONFLICT (handle) DO NOTHING
                """
            ),
            {
                "handle": handle,
                "display_name": "Test Publisher",
                "owner_address": account.address.lower(),
                "description": "Test",
                "recipient_address": recipient_address,
                "article_price": Decimal("0.50"),
                "subscription_price": Decimal("5.00"),
            },
        )

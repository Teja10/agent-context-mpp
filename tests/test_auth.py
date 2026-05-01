from uuid import UUID

from eth_account import Account
from eth_account.messages import encode_defunct
from eth_account.signers.local import LocalAccount
from mpp import Challenge
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine

from app.db.queries import upsert_wallet_principal
from app.db.schema import publishers
from conftest import (
    MPP_SECRET_KEY,
    RouteClient,
    wallet_count,
)


AUTH_REALM = "agent-context"


def _create_challenge(client: RouteClient) -> str:
    """Request a challenge nonce from the server."""
    response = client.client.post("/auth/challenge")
    assert response.status_code == 200
    data = response.json()
    assert "challenge" in data
    assert data["realm"] == AUTH_REALM
    return data["challenge"]


def _wallet_proof_header(nonce: str, account: LocalAccount) -> dict[str, str]:
    """Sign a nonce and return the Authorization header."""
    message = encode_defunct(text=nonce)
    signed = account.sign_message(message)
    signature = signed.signature.hex()
    return {"Authorization": f"WalletProof {nonce}.{signature}"}


def test_challenge_endpoint_returns_nonce(paid_client: RouteClient) -> None:
    nonce = _create_challenge(paid_client)

    challenge = Challenge(
        id=nonce,
        method="tempo",
        intent="auth",
        request={},
        realm=AUTH_REALM,
    )
    assert challenge.verify(MPP_SECRET_KEY, AUTH_REALM)


def test_valid_wallet_proof_upserts_principal(
    paid_client: RouteClient,
) -> None:
    account = Account.create()
    nonce = _create_challenge(paid_client)
    headers = _wallet_proof_header(nonce, account)

    _insert_publisher_for_account(paid_client.engine, account)
    response = paid_client.client.patch(
        "/publishers/test-handle",
        json={"display_name": "New Name"},
        headers=headers,
    )

    assert response.status_code == 200
    assert wallet_count(paid_client.engine) >= 1


def test_invalid_signature_returns_401(paid_client: RouteClient) -> None:
    nonce = _create_challenge(paid_client)
    headers = {"Authorization": f"WalletProof {nonce}.deadbeef"}

    response = paid_client.client.patch(
        "/publishers/test-handle",
        json={"display_name": "Bad"},
        headers=headers,
    )

    assert response.status_code == 401


def test_bad_nonce_returns_401(paid_client: RouteClient) -> None:
    account = Account.create()
    bad_nonce = "not-a-valid-hmac-nonce"
    headers = _wallet_proof_header(bad_nonce, account)

    response = paid_client.client.patch(
        "/publishers/test-handle",
        json={"display_name": "Bad"},
        headers=headers,
    )

    assert response.status_code == 401


def test_missing_authorization_returns_401(paid_client: RouteClient) -> None:
    response = paid_client.client.patch(
        "/publishers/test-handle",
        json={"display_name": "Bad"},
    )

    assert response.status_code == 401


def test_publisher_owner_mutation_success(
    paid_client: RouteClient,
) -> None:
    account = Account.create()
    _insert_publisher_for_account(paid_client.engine, account)
    nonce = _create_challenge(paid_client)
    headers = _wallet_proof_header(nonce, account)

    response = paid_client.client.patch(
        "/publishers/test-handle",
        json={"display_name": "Updated Name"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json() == {
        "handle": "test-handle",
        "display_name": "Updated Name",
    }


def test_publisher_owner_mismatch_returns_403(
    paid_client: RouteClient,
) -> None:
    account = Account.create()
    nonce = _create_challenge(paid_client)
    headers = _wallet_proof_header(nonce, account)

    response = paid_client.client.patch(
        "/publishers/agent-context-research",
        json={"display_name": "Hijacked"},
        headers=headers,
    )

    assert response.status_code == 403


def test_publisher_not_found_returns_404(
    paid_client: RouteClient,
) -> None:
    account = Account.create()
    nonce = _create_challenge(paid_client)
    headers = _wallet_proof_header(nonce, account)

    response = paid_client.client.patch(
        "/publishers/nonexistent",
        json={"display_name": "Ghost"},
        headers=headers,
    )

    assert response.status_code == 404


def _insert_publisher_for_account(engine: Engine, account: LocalAccount) -> None:
    """Insert a test publisher whose recipient matches the account address."""
    upsert_wallet_principal(engine, account.address.lower())
    with engine.begin() as connection:
        connection.execute(
            insert(publishers)
            .values(
                id=UUID("55555555-5555-5555-5555-555555555555"),
                handle="test-handle",
                display_name="Test Publisher",
                recipient_address=account.address,
                created_at="now()",
            )
            .on_conflict_do_nothing(index_elements=[publishers.c.handle])
        )

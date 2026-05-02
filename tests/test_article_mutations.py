"""Tests for article draft, update, and publish endpoints."""

from datetime import date
from decimal import Decimal

from eth_account import Account
from eth_account.messages import encode_defunct
from eth_account.signers.local import LocalAccount
from sqlalchemy import text

from app.db.queries import get_article_by_slug_for_owner, upsert_wallet_principal
from conftest import RouteClient


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


DRAFT_MARKDOWN = """\
---
slug: my-draft
title: My Draft Article
author: Test Author
price: 0.50
license: CC-BY-4.0
summary: A test summary
tags:
  - test
  - draft
key_claims:
  - First claim
allowed_excerpts:
  - An excerpt
suggested_citation: "Cite this."
---
# My Draft

Body content here.
"""

MINIMAL_MARKDOWN = """\
---
slug: minimal-draft
title: Minimal Draft
---
Minimal body.
"""


def _setup_owned_publisher(client: RouteClient, account: LocalAccount) -> str:
    """Create a publisher owned by account, return the handle."""
    upsert_wallet_principal(client.engine, account.address.lower())
    handle = f"test-pub-{account.address[-8:].lower()}"
    with client.engine.begin() as connection:
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
                "recipient_address": account.address,
                "article_price": Decimal("0.50"),
                "subscription_price": Decimal("5.00"),
            },
        )
    return handle


def test_create_article_draft_success(paid_client: RouteClient) -> None:
    """POST /publishers/{handle}/articles creates a draft article."""
    account = Account.create()
    handle = _setup_owned_publisher(paid_client, account)
    headers = _auth_headers(paid_client, account)

    response = paid_client.client.post(
        f"/publishers/{handle}/articles",
        json={"markdown": DRAFT_MARKDOWN},
        headers=headers,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["slug"] == "my-draft"
    assert data["status"] == "draft"


def test_create_article_invalid_frontmatter(paid_client: RouteClient) -> None:
    """POST with invalid frontmatter returns 422."""
    account = Account.create()
    handle = _setup_owned_publisher(paid_client, account)
    headers = _auth_headers(paid_client, account)

    bad_markdown = "---\nunknown_field: bad\n---\nBody."
    response = paid_client.client.post(
        f"/publishers/{handle}/articles",
        json={"markdown": bad_markdown},
        headers=headers,
    )

    assert response.status_code == 422


def test_create_article_duplicate_slug(paid_client: RouteClient) -> None:
    """POST with duplicate slug returns 409."""
    account = Account.create()
    handle = _setup_owned_publisher(paid_client, account)
    headers = _auth_headers(paid_client, account)

    paid_client.client.post(
        f"/publishers/{handle}/articles",
        json={"markdown": DRAFT_MARKDOWN},
        headers=headers,
    )
    response = paid_client.client.post(
        f"/publishers/{handle}/articles",
        json={"markdown": DRAFT_MARKDOWN},
        headers=headers,
    )

    assert response.status_code == 409


def test_create_article_wrong_owner(paid_client: RouteClient) -> None:
    """POST by non-owner returns 403."""
    owner = Account.create()
    handle = _setup_owned_publisher(paid_client, owner)
    intruder = Account.create()
    headers = _auth_headers(paid_client, intruder)

    response = paid_client.client.post(
        f"/publishers/{handle}/articles",
        json={"markdown": DRAFT_MARKDOWN},
        headers=headers,
    )

    assert response.status_code == 403


def test_update_article_success(paid_client: RouteClient) -> None:
    """PATCH /articles/{slug} updates body and metadata."""
    account = Account.create()
    handle = _setup_owned_publisher(paid_client, account)
    headers = _auth_headers(paid_client, account)

    paid_client.client.post(
        f"/publishers/{handle}/articles",
        json={"markdown": DRAFT_MARKDOWN},
        headers=headers,
    )
    updated_markdown = """\
---
slug: my-draft
title: Updated Title
author: New Author
price: 1.00
license: MIT
summary: Updated summary
tags:
  - updated
key_claims:
  - Updated claim
allowed_excerpts:
  - Updated excerpt
suggested_citation: "Updated cite."
---
# Updated

Updated body.
"""
    response = paid_client.client.patch(
        "/articles/my-draft",
        json={"markdown": updated_markdown},
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["slug"] == "my-draft"
    assert data["status"] == "draft"

    record = get_article_by_slug_for_owner(paid_client.engine, "my-draft")
    assert record is not None
    assert record.title == "Updated Title"
    assert record.author == "New Author"
    assert record.body == "# Updated\n\nUpdated body."


def test_update_article_wrong_owner(paid_client: RouteClient) -> None:
    """PATCH by non-owner returns 403."""
    owner = Account.create()
    handle = _setup_owned_publisher(paid_client, owner)
    owner_headers = _auth_headers(paid_client, owner)

    paid_client.client.post(
        f"/publishers/{handle}/articles",
        json={"markdown": DRAFT_MARKDOWN},
        headers=owner_headers,
    )
    intruder = Account.create()
    intruder_headers = _auth_headers(paid_client, intruder)

    response = paid_client.client.patch(
        "/articles/my-draft",
        json={"markdown": DRAFT_MARKDOWN},
        headers=intruder_headers,
    )

    assert response.status_code == 403


def test_update_article_not_found(paid_client: RouteClient) -> None:
    """PATCH for nonexistent slug returns 404."""
    account = Account.create()
    headers = _auth_headers(paid_client, account)

    response = paid_client.client.patch(
        "/articles/nonexistent-slug",
        json={"markdown": DRAFT_MARKDOWN},
        headers=headers,
    )

    assert response.status_code == 404


def test_publish_article_success(paid_client: RouteClient) -> None:
    """POST /articles/{slug}/publish sets status to published with published_at."""
    account = Account.create()
    handle = _setup_owned_publisher(paid_client, account)
    headers = _auth_headers(paid_client, account)

    paid_client.client.post(
        f"/publishers/{handle}/articles",
        json={"markdown": DRAFT_MARKDOWN},
        headers=headers,
    )
    response = paid_client.client.post(
        "/articles/my-draft/publish",
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "published"

    record = get_article_by_slug_for_owner(paid_client.engine, "my-draft")
    assert record is not None
    assert record.status == "published"
    assert record.published_date == date.today()

    detail_response = paid_client.client.get("/articles/my-draft")
    assert detail_response.status_code == 200


def test_publish_missing_required_field(paid_client: RouteClient) -> None:
    """POST publish with missing fields returns 422."""
    account = Account.create()
    handle = _setup_owned_publisher(paid_client, account)
    headers = _auth_headers(paid_client, account)

    paid_client.client.post(
        f"/publishers/{handle}/articles",
        json={"markdown": MINIMAL_MARKDOWN},
        headers=headers,
    )
    response = paid_client.client.post(
        "/articles/minimal-draft/publish",
        headers=headers,
    )

    assert response.status_code == 422


def test_publish_wrong_owner(paid_client: RouteClient) -> None:
    """POST publish by non-owner returns 403."""
    owner = Account.create()
    handle = _setup_owned_publisher(paid_client, owner)
    owner_headers = _auth_headers(paid_client, owner)

    paid_client.client.post(
        f"/publishers/{handle}/articles",
        json={"markdown": DRAFT_MARKDOWN},
        headers=owner_headers,
    )
    intruder = Account.create()
    intruder_headers = _auth_headers(paid_client, intruder)

    response = paid_client.client.post(
        "/articles/my-draft/publish",
        headers=intruder_headers,
    )

    assert response.status_code == 403


def test_draft_not_in_article_list(paid_client: RouteClient) -> None:
    """GET /articles excludes draft articles."""
    account = Account.create()
    handle = _setup_owned_publisher(paid_client, account)
    headers = _auth_headers(paid_client, account)

    paid_client.client.post(
        f"/publishers/{handle}/articles",
        json={"markdown": DRAFT_MARKDOWN},
        headers=headers,
    )
    response = paid_client.client.get("/articles")

    assert response.status_code == 200
    slugs = [a["slug"] for a in response.json()]
    assert "my-draft" not in slugs


def test_draft_slug_returns_404(paid_client: RouteClient) -> None:
    """GET /articles/{slug} returns 404 for draft articles."""
    account = Account.create()
    handle = _setup_owned_publisher(paid_client, account)
    headers = _auth_headers(paid_client, account)

    paid_client.client.post(
        f"/publishers/{handle}/articles",
        json={"markdown": DRAFT_MARKDOWN},
        headers=headers,
    )
    response = paid_client.client.get("/articles/my-draft")

    assert response.status_code == 404

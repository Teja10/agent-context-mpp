"""Tests for publisher-workspace list/fetch endpoints."""

import frontmatter  # type: ignore[import-untyped]
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_account.signers.local import LocalAccount

from conftest import (
    ARTICLE_B_SLUG,
    ARTICLE_SLUG,
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


def _create_publisher(client: RouteClient, account: LocalAccount, handle: str) -> None:
    response = client.client.post(
        "/publishers",
        json={
            "handle": handle,
            "display_name": "Test Publisher",
            "description": "Test",
            "default_article_price": "0.50",
            "default_subscription_price": "5.00",
        },
        headers=_auth_headers(client, account),
    )
    assert response.status_code == 201


DRAFT_MARKDOWN = """\
---
slug: workspace-draft
title: Workspace Draft
author: Test Author
price: 0.75
license: CC-BY-4.0
summary: Editor reload test
tags:
  - test
key_claims:
  - A claim
allowed_excerpts:
  - An excerpt
suggested_citation: "Cite this."
---
# Heading

Body content for editor reload.
"""


def test_me_publishers_returns_owned_only(paid_client: RouteClient) -> None:
    account = Account.create()
    _create_publisher(paid_client, account, "owned-by-me")

    response = paid_client.client.get(
        "/me/publishers", headers=_auth_headers(paid_client, account)
    )

    assert response.status_code == 200
    handles = [pub["handle"] for pub in response.json()]
    assert handles == ["owned-by-me"]


def test_me_publishers_excludes_other_owners(paid_client: RouteClient) -> None:
    other = Account.create()
    response = paid_client.client.get(
        "/me/publishers", headers=_auth_headers(paid_client, other)
    )

    assert response.status_code == 200
    assert response.json() == []


def test_me_publishers_requires_auth(paid_client: RouteClient) -> None:
    response = paid_client.client.get("/me/publishers")
    assert response.status_code == 401


def test_list_publisher_articles_unauthenticated_published_only(
    paid_client: RouteClient,
) -> None:
    response = paid_client.client.get("/publishers/agent-context-research/articles")

    assert response.status_code == 200
    slugs = [a["slug"] for a in response.json()]
    assert ARTICLE_SLUG in slugs
    assert ARTICLE_B_SLUG not in slugs
    for entry in response.json():
        assert entry["status"] == "published"


def test_list_publisher_articles_owner_includes_drafts(
    paid_client: RouteClient,
) -> None:
    account = Account.create()
    _create_publisher(paid_client, account, "drafts-pub")
    headers = _auth_headers(paid_client, account)
    paid_client.client.post(
        "/publishers/drafts-pub/articles",
        json={"markdown": DRAFT_MARKDOWN},
        headers=headers,
    )

    response = paid_client.client.get(
        "/publishers/drafts-pub/articles",
        headers=_auth_headers(paid_client, account),
    )

    assert response.status_code == 200
    statuses = {a["slug"]: a["status"] for a in response.json()}
    assert statuses == {"workspace-draft": "draft"}


def test_list_publisher_articles_non_owner_excludes_drafts(
    paid_client: RouteClient,
) -> None:
    owner = Account.create()
    _create_publisher(paid_client, owner, "drafts-pub-2")
    paid_client.client.post(
        "/publishers/drafts-pub-2/articles",
        json={"markdown": DRAFT_MARKDOWN},
        headers=_auth_headers(paid_client, owner),
    )
    intruder = Account.create()

    response = paid_client.client.get(
        "/publishers/drafts-pub-2/articles",
        headers=_auth_headers(paid_client, intruder),
    )

    assert response.status_code == 200
    assert response.json() == []


def test_list_publisher_articles_publisher_not_found(
    paid_client: RouteClient,
) -> None:
    response = paid_client.client.get("/publishers/no-such-pub/articles")
    assert response.status_code == 404


def test_get_owned_article_returns_roundtrippable_markdown(
    paid_client: RouteClient,
) -> None:
    account = Account.create()
    _create_publisher(paid_client, account, "editor-pub")
    headers = _auth_headers(paid_client, account)
    paid_client.client.post(
        "/publishers/editor-pub/articles",
        json={"markdown": DRAFT_MARKDOWN},
        headers=headers,
    )

    response = paid_client.client.get(
        "/publishers/editor-pub/articles/workspace-draft",
        headers=_auth_headers(paid_client, account),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "draft"
    parsed = frontmatter.loads(data["markdown"])
    assert parsed.metadata["title"] == "Workspace Draft"
    assert parsed.metadata["slug"] == "workspace-draft"
    assert parsed.metadata["price"] == "0.75"
    assert parsed.metadata["tags"] == ["test"]
    assert parsed.content == "# Heading\n\nBody content for editor reload."


def test_get_owned_article_non_owner_returns_403(paid_client: RouteClient) -> None:
    owner = Account.create()
    _create_publisher(paid_client, owner, "editor-pub-2")
    paid_client.client.post(
        "/publishers/editor-pub-2/articles",
        json={"markdown": DRAFT_MARKDOWN},
        headers=_auth_headers(paid_client, owner),
    )
    intruder = Account.create()

    response = paid_client.client.get(
        "/publishers/editor-pub-2/articles/workspace-draft",
        headers=_auth_headers(paid_client, intruder),
    )

    assert response.status_code == 403


def test_get_owned_article_unknown_slug_returns_404(
    paid_client: RouteClient,
) -> None:
    account = Account.create()
    _create_publisher(paid_client, account, "editor-pub-3")

    response = paid_client.client.get(
        "/publishers/editor-pub-3/articles/missing",
        headers=_auth_headers(paid_client, account),
    )

    assert response.status_code == 404


def test_get_owned_article_requires_auth(paid_client: RouteClient) -> None:
    response = paid_client.client.get(
        f"/publishers/agent-context-research/articles/{ARTICLE_SLUG}"
    )
    assert response.status_code == 401

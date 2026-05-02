from pydantic import TypeAdapter

from app.db.queries import lookup_purchase_by_payment_reference
from app.db.records import OneTimePurchase
from app.models import ArticleMetadata, ContextPackage
from mpp import Receipt
from conftest import (
    ARTICLE_SLUG,
    CURRENCY,
    NETWORK,
    PAID_HEADERS,
    PUBLISHER_RECIPIENT,
    RECEIPT_PAYLOAD,
    TX_HASH,
    ChargeCall,
    RouteClient,
    purchase_count,
)

ARTICLE_LIST_ADAPTER = TypeAdapter(list[ArticleMetadata])


def test_health_returns_ok(challenge_client: RouteClient) -> None:
    response = challenge_client.client.get("/health")

    assert response.status_code == 200
    assert TypeAdapter(dict[str, str]).validate_python(response.json()) == {
        "status": "ok"
    }


def test_articles_returns_metadata(challenge_client: RouteClient) -> None:
    response = challenge_client.client.get("/articles")

    assert response.status_code == 200
    articles = ARTICLE_LIST_ADAPTER.validate_python(response.json())
    assert [article.slug for article in articles] == [
        "ai-agent-payments",
        "context-for-machines",
        "decentralized-identity",
        "publisher-b-article",
    ]


def test_article_detail_returns_metadata(challenge_client: RouteClient) -> None:
    response = challenge_client.client.get(f"/articles/{ARTICLE_SLUG}")

    assert response.status_code == 200
    article = ArticleMetadata.model_validate(response.json())
    assert article.slug == ARTICLE_SLUG
    assert article.price == str(challenge_client.articles[ARTICLE_SLUG].price)


def test_unknown_article_detail_returns_404(challenge_client: RouteClient) -> None:
    response = challenge_client.client.get("/articles/unknown")

    assert response.status_code == 404


def test_context_without_authorization_returns_payment_challenge(
    challenge_client: RouteClient,
) -> None:
    response = challenge_client.client.get(f"/articles/{ARTICLE_SLUG}/context")

    assert response.status_code == 402
    assert response.headers["WWW-Authenticate"].startswith("Payment ")
    assert challenge_client.mpp.calls == [
        ChargeCall(
            authorization=None,
            amount=str(challenge_client.articles[ARTICLE_SLUG].price),
            memo="0x4709280c7c375e35bb5c1dc5beba9fd25ddc8743c6959facf650ef0c6e3ab785",
            recipient=PUBLISHER_RECIPIENT,
        )
    ]


def test_paid_context_returns_context_package(paid_client: RouteClient) -> None:
    response = paid_client.client.get(
        f"/articles/{ARTICLE_SLUG}/context", headers=PAID_HEADERS
    )

    assert response.status_code == 200
    context = ContextPackage.model_validate(response.json())
    article = paid_client.articles[ARTICLE_SLUG]
    assert context.summary == article.summary
    assert context.key_claims == article.key_claims
    assert context.allowed_excerpts == article.allowed_excerpts
    assert context.suggested_citation == article.suggested_citation
    assert context.license == article.license
    assert context.receipt == RECEIPT_PAYLOAD
    assert (
        Receipt.from_payment_receipt(response.headers["Payment-Receipt"]).reference
        == TX_HASH
    )


def test_paid_context_persists_purchase(paid_client: RouteClient) -> None:
    article = paid_client.articles[ARTICLE_SLUG]
    assert article.price is not None

    response = paid_client.client.get(
        f"/articles/{ARTICLE_SLUG}/context", headers=PAID_HEADERS
    )

    assert response.status_code == 200
    assert lookup_purchase_by_payment_reference(
        paid_client.engine, TX_HASH
    ) == OneTimePurchase(
        article_slug=article.slug,
        wallet_address="0xpayer",
        payment_reference=TX_HASH,
        amount=article.price,
        currency=CURRENCY,
        network=NETWORK,
        recipient_wallet=PUBLISHER_RECIPIENT.lower(),
        receipt=RECEIPT_PAYLOAD,
    )


def test_same_tx_hash_replay_returns_existing_purchase_without_second_row(
    paid_client: RouteClient,
) -> None:
    first_response = paid_client.client.get(
        f"/articles/{ARTICLE_SLUG}/context", headers=PAID_HEADERS
    )
    second_response = paid_client.client.get(
        f"/articles/{ARTICLE_SLUG}/context", headers=PAID_HEADERS
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert ContextPackage.model_validate(first_response.json()) == (
        ContextPackage.model_validate(second_response.json())
    )
    assert purchase_count(paid_client.engine) == 1

"""Article listing, draft creation, update, and publish endpoints."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Annotated, Optional
from uuid import uuid4

import frontmatter  # type: ignore[import-untyped]
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.auth import (
    WalletPrincipal,
    optional_wallet_principal,
    require_wallet_principal,
)
from app.db.queries import (
    get_article_by_publisher_and_slug,
    get_article_by_slug,
    get_publisher_by_handle,
    insert_article,
    list_article_metadata,
    list_articles_by_publisher,
    publish_article,
    update_article,
)
from app.db.records import ArticleRecord, PublisherRecord
from app.models import ArticleMetadata
from app.state import AppState, get_state

router = APIRouter()


class ArticleFrontmatter(BaseModel):
    """Validated frontmatter fields parsed from Markdown."""

    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=1)
    title: str = Field(min_length=1)
    author: Optional[str] = None
    price: Optional[Decimal] = None
    license: Optional[str] = None
    summary: Optional[str] = None
    tags: Optional[list[str]] = None
    key_claims: Optional[list[str]] = None
    allowed_excerpts: Optional[list[str]] = None
    suggested_citation: Optional[str] = None


class MarkdownBody(BaseModel):
    """Request body containing a Markdown document with frontmatter."""

    model_config = ConfigDict(extra="forbid")

    markdown: str


@dataclass(frozen=True)
class ParsedMarkdown:
    """Frontmatter and body extracted from a Markdown document."""

    meta: ArticleFrontmatter
    body: str


def _parse_frontmatter(markdown: str) -> ParsedMarkdown:
    """Parse and validate frontmatter from a Markdown string.

    Args:
        markdown: Raw Markdown with YAML frontmatter.

    Returns:
        Parsed and validated frontmatter with body text.

    Raises:
        HTTPException: 422 if frontmatter is invalid.
    """
    post = frontmatter.loads(markdown)
    try:
        fm = ArticleFrontmatter.model_validate(post.metadata)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())
    return ParsedMarkdown(meta=fm, body=post.content)


def _serialize_markdown(article: ArticleRecord) -> str:
    """Reconstruct the markdown document (frontmatter + body) for an article."""
    metadata: dict[str, object] = {"slug": article.slug, "title": article.title}
    optional_fields: list[tuple[str, object]] = [
        ("author", article.author),
        ("price", str(article.price) if article.price is not None else None),
        ("license", article.license),
        ("summary", article.summary),
        ("tags", article.tags),
        ("key_claims", article.key_claims),
        ("allowed_excerpts", article.allowed_excerpts),
        ("suggested_citation", article.suggested_citation),
    ]
    for key, value in optional_fields:
        if value is not None:
            metadata[key] = value
    post = frontmatter.Post(article.body)
    post.metadata = metadata
    return frontmatter.dumps(post)


def _require_owned_publisher(
    state: AppState, handle: str, principal: WalletPrincipal
) -> PublisherRecord:
    """Load a publisher by handle and verify the principal owns it."""
    publisher = get_publisher_by_handle(state.engine, handle)
    if publisher is None:
        raise HTTPException(status_code=404, detail="Publisher not found")
    if principal.wallet_address != publisher.owner_address:
        raise HTTPException(status_code=403, detail="Wallet does not own publisher")
    return publisher


def _require_owned_article(
    state: AppState, handle: str, slug: str, principal: WalletPrincipal
) -> tuple[PublisherRecord, ArticleRecord]:
    """Load (publisher, article) and verify the principal owns the publisher."""
    publisher = _require_owned_publisher(state, handle, principal)
    article = get_article_by_publisher_and_slug(state.engine, publisher.id, slug)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return publisher, article


@router.get("/articles")
def get_articles(
    state: Annotated[AppState, Depends(get_state)],
) -> list[ArticleMetadata]:
    """Return public metadata for all published articles."""
    return list_article_metadata(state.engine)


@router.get("/articles/{slug}")
def get_article(
    slug: str,
    state: Annotated[AppState, Depends(get_state)],
) -> ArticleMetadata:
    """Return public metadata for one published article."""
    article = get_article_by_slug(state.engine, slug)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return article.metadata


def _article_summary(article: ArticleRecord) -> dict[str, object]:
    """Serialize a list-view article entry for publisher dashboards."""
    return {
        "slug": article.slug,
        "title": article.title,
        "status": article.status,
        "price": str(article.price) if article.price is not None else None,
        "published_at": (
            article.published_at.isoformat()
            if article.published_at is not None
            else None
        ),
    }


@router.get("/publishers/{handle}/articles")
def list_publisher_articles(
    handle: str,
    state: Annotated[AppState, Depends(get_state)],
    principal: Annotated[Optional[WalletPrincipal], Depends(optional_wallet_principal)],
) -> list[dict[str, object]]:
    """List a publisher's articles. Owner sees drafts; others see published only."""
    publisher = get_publisher_by_handle(state.engine, handle)
    if publisher is None:
        raise HTTPException(status_code=404, detail="Publisher not found")
    is_owner = (
        principal is not None and principal.wallet_address == publisher.owner_address
    )
    return [
        _article_summary(article)
        for article in list_articles_by_publisher(
            state.engine, publisher.id, include_drafts=is_owner
        )
    ]


@router.post("/publishers/{handle}/articles", status_code=201)
def create_article_draft(
    handle: str,
    body: MarkdownBody,
    state: Annotated[AppState, Depends(get_state)],
    principal: Annotated[WalletPrincipal, Depends(require_wallet_principal)],
) -> dict[str, object]:
    """Create a draft article from Markdown with frontmatter."""
    publisher = _require_owned_publisher(state, handle, principal)
    parsed = _parse_frontmatter(body.markdown)
    fm = parsed.meta
    record = insert_article(
        state.engine,
        article_id=uuid4(),
        publisher_id=publisher.id,
        slug=fm.slug,
        title=fm.title,
        body=parsed.body,
        author=fm.author,
        price=fm.price,
        license=fm.license,
        summary=fm.summary,
        tags=fm.tags,
        key_claims=fm.key_claims,
        allowed_excerpts=fm.allowed_excerpts,
        suggested_citation=fm.suggested_citation,
    )
    if record is None:
        raise HTTPException(status_code=409, detail="Slug already exists")
    return {"id": str(record.id), "slug": record.slug, "status": record.status}


@router.get("/publishers/{handle}/articles/{slug}")
def get_owned_article(
    handle: str,
    slug: str,
    state: Annotated[AppState, Depends(get_state)],
    principal: Annotated[WalletPrincipal, Depends(require_wallet_principal)],
) -> dict[str, object]:
    """Return the markdown document for an owned article (draft or published)."""
    _, article = _require_owned_article(state, handle, slug, principal)
    return {
        "slug": article.slug,
        "status": article.status,
        "markdown": _serialize_markdown(article),
    }


@router.patch("/publishers/{handle}/articles/{slug}")
def patch_article(
    handle: str,
    slug: str,
    body: MarkdownBody,
    state: Annotated[AppState, Depends(get_state)],
    principal: Annotated[WalletPrincipal, Depends(require_wallet_principal)],
) -> dict[str, object]:
    """Update an existing article from Markdown with frontmatter."""
    publisher, article = _require_owned_article(state, handle, slug, principal)
    parsed = _parse_frontmatter(body.markdown)
    fm = parsed.meta
    values: dict[str, object] = {
        "slug": fm.slug,
        "title": fm.title,
        "body": parsed.body,
        "author": fm.author,
        "price": fm.price,
        "license": fm.license,
        "summary": fm.summary,
        "tags": fm.tags,
        "key_claims": fm.key_claims,
        "allowed_excerpts": fm.allowed_excerpts,
        "suggested_citation": fm.suggested_citation,
    }
    update_article(state.engine, slug, publisher.id, values)
    return {"slug": fm.slug, "status": article.status}


@router.post("/publishers/{handle}/articles/{slug}/publish")
def publish_article_route(
    handle: str,
    slug: str,
    state: Annotated[AppState, Depends(get_state)],
    principal: Annotated[WalletPrincipal, Depends(require_wallet_principal)],
) -> dict[str, object]:
    """Publish a draft article after validating required fields."""
    publisher, article = _require_owned_article(state, handle, slug, principal)
    missing: list[str] = []
    if not article.title:
        missing.append("title")
    if not article.slug:
        missing.append("slug")
    if not article.author:
        missing.append("author")
    if not article.summary:
        missing.append("summary")
    if not article.tags:
        missing.append("tags")
    if article.price is None or article.price <= 0:
        missing.append("price")
    if not article.license:
        missing.append("license")
    if not article.key_claims:
        missing.append("key_claims")
    if not article.allowed_excerpts:
        missing.append("allowed_excerpts")
    if not article.suggested_citation:
        missing.append("suggested_citation")
    if missing:
        raise HTTPException(
            status_code=422, detail=f"Missing required fields: {', '.join(missing)}"
        )
    publish_article(state.engine, slug, publisher.id)
    return {"slug": article.slug, "status": "published"}

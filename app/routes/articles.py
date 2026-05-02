"""Article listing, draft creation, update, and publish endpoints."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Annotated, Optional
from uuid import uuid4

import frontmatter  # type: ignore[import-untyped]
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, ValidationError

from app.auth import WalletPrincipal, require_wallet_principal
from app.db.queries import (
    get_article_by_slug,
    get_article_by_slug_for_owner,
    get_publisher_by_handle,
    get_publisher_by_id,
    insert_article,
    list_article_metadata,
    publish_article,
    update_article,
)
from app.db.records import ArticleRecord
from app.models import ArticleMetadata
from app.state import AppState, get_state

router = APIRouter()


class ArticleFrontmatter(BaseModel):
    """Validated frontmatter fields parsed from Markdown."""

    model_config = ConfigDict(extra="forbid")

    slug: str
    title: str
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


@router.post("/publishers/{handle}/articles", status_code=201)
def create_article_draft(
    handle: str,
    body: MarkdownBody,
    state: Annotated[AppState, Depends(get_state)],
    principal: Annotated[WalletPrincipal, Depends(require_wallet_principal)],
) -> dict[str, object]:
    """Create a draft article from Markdown with frontmatter.

    Args:
        handle: Publisher handle.
        body: Request body with markdown field.
        state: Application state.
        principal: Authenticated wallet principal.

    Returns:
        Created article fields.

    Raises:
        HTTPException: 404 publisher not found, 403 wrong owner,
            422 bad frontmatter, 409 slug conflict.
    """
    publisher = get_publisher_by_handle(state.engine, handle)
    if publisher is None:
        raise HTTPException(status_code=404, detail="Publisher not found")
    if principal.wallet_address != publisher.owner_address:
        raise HTTPException(status_code=403, detail="Wallet does not own publisher")
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


def _require_owned_article(
    state: AppState, slug: str, principal: WalletPrincipal
) -> ArticleRecord:
    """Load an article and verify ownership, raising on 404/403.

    Args:
        state: Application state.
        slug: Article slug.
        principal: Authenticated wallet principal.

    Returns:
        ArticleRecord owned by the principal.

    Raises:
        HTTPException: 404 if not found, 403 if not owner.
    """
    article = get_article_by_slug_for_owner(state.engine, slug)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    publisher = get_publisher_by_id(state.engine, article.publisher_id)
    if publisher is None:
        raise RuntimeError(f"Article {article.id} has no publisher")
    if principal.wallet_address != publisher.owner_address:
        raise HTTPException(status_code=403, detail="Wallet does not own publisher")
    return article


@router.patch("/articles/{slug}")
def patch_article(
    slug: str,
    body: MarkdownBody,
    state: Annotated[AppState, Depends(get_state)],
    principal: Annotated[WalletPrincipal, Depends(require_wallet_principal)],
) -> dict[str, object]:
    """Update an existing article from Markdown with frontmatter.

    Args:
        slug: Article slug (URL lookup key).
        body: Request body with markdown field.
        state: Application state.
        principal: Authenticated wallet principal.

    Returns:
        Updated article slug and status.

    Raises:
        HTTPException: 404 not found, 403 wrong owner, 422 bad frontmatter.
    """
    article = _require_owned_article(state, slug, principal)
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
    update_article(state.engine, slug, article.publisher_id, values)
    return {"slug": fm.slug, "status": article.status}


@router.post("/articles/{slug}/publish")
def publish_article_route(
    slug: str,
    state: Annotated[AppState, Depends(get_state)],
    principal: Annotated[WalletPrincipal, Depends(require_wallet_principal)],
) -> dict[str, object]:
    """Publish a draft article after validating required fields.

    Args:
        slug: Article slug.
        state: Application state.
        principal: Authenticated wallet principal.

    Returns:
        Published article slug and status.

    Raises:
        HTTPException: 404 not found, 403 wrong owner,
            422 missing required fields.
    """
    article = _require_owned_article(state, slug, principal)
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
    publish_article(state.engine, slug, article.publisher_id)
    return {"slug": article.slug, "status": "published"}

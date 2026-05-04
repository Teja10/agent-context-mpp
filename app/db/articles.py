"""Article query functions."""

from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine, RowMapping

from app.db.records import ArticleRecord
from app.db.schema import articles, publishers
from app.models import ArticleMetadata


def list_article_metadata(engine: Engine) -> list[ArticleMetadata]:
    """Return public metadata for all published articles ordered by slug."""
    with engine.connect() as connection:
        rows = connection.execute(
            select(
                articles.c.title,
                articles.c.author,
                articles.c.published_at,
                articles.c.price,
                articles.c.slug,
            )
            .where(articles.c.status == "published")
            .order_by(articles.c.slug)
        )
        return [
            ArticleMetadata(
                title=row["title"],
                author=row["author"],
                published_date=row["published_at"],
                price=str(row["price"]),
                slug=row["slug"],
            )
            for row in rows.mappings()
        ]


def list_articles(engine: Engine) -> list[ArticleRecord]:
    """Return all articles ordered by slug, joined with their publishers."""
    with engine.connect() as connection:
        rows = connection.execute(
            select(
                articles,
                publishers.c.recipient_address.label("publisher_recipient_address"),
            )
            .select_from(
                articles.join(publishers, articles.c.publisher_id == publishers.c.id)
            )
            .order_by(articles.c.slug)
        )
        return [_article_record(row) for row in rows.mappings()]


def get_article_by_slug(engine: Engine, slug: str) -> Optional[ArticleRecord]:
    """Return one published article by its slug, joined with its publisher."""
    with engine.connect() as connection:
        row = (
            connection.execute(
                select(
                    articles,
                    publishers.c.recipient_address.label("publisher_recipient_address"),
                )
                .select_from(
                    articles.join(
                        publishers, articles.c.publisher_id == publishers.c.id
                    )
                )
                .where(articles.c.slug == slug)
                .where(articles.c.status == "published")
            )
            .mappings()
            .one_or_none()
        )
    if row is None:
        return None
    return _article_record(row)


def get_article_by_slug_for_owner(engine: Engine, slug: str) -> Optional[ArticleRecord]:
    """Return one article by slug regardless of status, joined with its publisher.

    Args:
        engine: SQLAlchemy engine.
        slug: Article slug.

    Returns:
        ArticleRecord if found, None otherwise.
    """
    with engine.connect() as connection:
        row = (
            connection.execute(
                select(
                    articles,
                    publishers.c.recipient_address.label("publisher_recipient_address"),
                )
                .select_from(
                    articles.join(
                        publishers, articles.c.publisher_id == publishers.c.id
                    )
                )
                .where(articles.c.slug == slug)
            )
            .mappings()
            .one_or_none()
        )
    if row is None:
        return None
    return _article_record(row)


def insert_article(
    engine: Engine,
    article_id: UUID,
    publisher_id: UUID,
    slug: str,
    title: str,
    body: str,
    author: Optional[str],
    price: Optional[Decimal],
    license: Optional[str],
    summary: Optional[str],
    tags: Optional[list[str]],
    key_claims: Optional[list[str]],
    allowed_excerpts: Optional[list[str]],
    suggested_citation: Optional[str],
) -> Optional[ArticleRecord]:
    """Insert a draft article. Return None on (publisher_id, slug) conflict.

    Args:
        engine: SQLAlchemy engine.
        article_id: UUID for the new article.
        publisher_id: Publisher that owns the article.
        slug: URL slug.
        title: Article title.
        body: Markdown body text.
        author: Optional author name.
        price: Optional price.
        license: Optional license string.
        summary: Optional summary.
        tags: Optional list of tags.
        key_claims: Optional list of key claims.
        allowed_excerpts: Optional list of allowed excerpts.
        suggested_citation: Optional citation string.

    Returns:
        ArticleRecord if inserted, None if slug conflict.
    """
    with engine.begin() as connection:
        inserted_slug = connection.execute(
            insert(articles)
            .values(
                id=article_id,
                publisher_id=publisher_id,
                slug=slug,
                title=title,
                status="draft",
                author=author,
                price=price,
                license=license,
                summary=summary,
                tags=tags,
                key_claims=key_claims,
                allowed_excerpts=allowed_excerpts,
                suggested_citation=suggested_citation,
                body=body,
                created_at=text("now()"),
                updated_at=text("now()"),
            )
            .on_conflict_do_nothing(
                constraint="articles_publisher_slug_key",
            )
            .returning(articles.c.slug)
        ).scalar_one_or_none()
    if inserted_slug is None:
        return None
    return get_article_by_slug_for_owner(engine, inserted_slug)


def update_article(
    engine: Engine, slug: str, publisher_id: UUID, values: dict[str, object]
) -> None:
    """Update article fields by slug and publisher_id.

    Args:
        engine: SQLAlchemy engine.
        slug: Article slug.
        publisher_id: Publisher UUID (ownership filter).
        values: Column-value pairs to update.
    """
    values["updated_at"] = text("now()")
    with engine.begin() as connection:
        connection.execute(
            update(articles)
            .where(articles.c.slug == slug)
            .where(articles.c.publisher_id == publisher_id)
            .values(**values)
        )


def publish_article(engine: Engine, slug: str, publisher_id: UUID) -> None:
    """Set article status to published with current date.

    Args:
        engine: SQLAlchemy engine.
        slug: Article slug.
        publisher_id: Publisher UUID (ownership filter).
    """
    with engine.begin() as connection:
        connection.execute(
            update(articles)
            .where(articles.c.slug == slug)
            .where(articles.c.publisher_id == publisher_id)
            .values(
                status="published",
                published_at=date.today(),
                updated_at=text("now()"),
            )
        )


def _article_record(row: RowMapping) -> ArticleRecord:
    return ArticleRecord(
        id=row["id"],
        publisher_id=row["publisher_id"],
        title=row["title"],
        status=row["status"],
        author=row["author"],
        published_date=row["published_at"],
        price=row["price"],
        license=row["license"],
        summary=row["summary"],
        tags=list(row["tags"]) if row["tags"] is not None else None,
        key_claims=list(row["key_claims"]) if row["key_claims"] is not None else None,
        allowed_excerpts=(
            list(row["allowed_excerpts"])
            if row["allowed_excerpts"] is not None
            else None
        ),
        suggested_citation=row["suggested_citation"],
        slug=row["slug"],
        body=row["body"],
        publisher_recipient_address=row["publisher_recipient_address"],
    )

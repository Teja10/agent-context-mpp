from fastapi import APIRouter, HTTPException
from sqlalchemy.engine import Engine

from app.db import ArticleRecord, get_article_by_slug, list_articles as list_db_articles
from app.models import ArticleMetadata

router = APIRouter()

_engine: Engine | None = None


def set_engine(engine: Engine) -> None:
    """Set article route database resources loaded during startup."""
    global _engine
    _engine = engine


@router.get("/articles")
async def list_articles() -> list[ArticleMetadata]:
    """Return public metadata for all stored articles."""
    return [_metadata(article) for article in list_db_articles(_loaded_engine())]


@router.get("/articles/{slug}")
async def get_article(slug: str) -> ArticleMetadata:
    """Return public metadata for one stored article."""
    article = get_article_by_slug(_loaded_engine(), slug)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return _metadata(article)


def _loaded_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("Database engine was not loaded during startup")
    return _engine


def _metadata(article: ArticleRecord) -> ArticleMetadata:
    return ArticleMetadata(
        title=article.title,
        author=article.author,
        published_date=article.published_date,
        price=str(article.price),
        slug=article.slug,
    )

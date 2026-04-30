from fastapi import APIRouter, HTTPException

from app.articles import Article
from app.models import ArticleMetadata

router = APIRouter()

_articles: dict[str, Article] | None = None


def set_articles(articles: dict[str, Article]) -> None:
    """Set articles loaded during application startup."""
    global _articles
    _articles = articles


@router.get("/articles")
async def list_articles() -> list[ArticleMetadata]:
    """Return public metadata for all loaded articles."""
    return [_metadata(article) for article in _loaded_articles().values()]


@router.get("/articles/{slug}")
async def get_article(slug: str) -> ArticleMetadata:
    """Return public metadata for one loaded article."""
    articles = _loaded_articles()
    if slug not in articles:
        raise HTTPException(status_code=404, detail="Article not found")
    return _metadata(articles[slug])


def _loaded_articles() -> dict[str, Article]:
    if _articles is None:
        raise RuntimeError("Articles were not loaded during startup")
    return _articles


def _metadata(article: Article) -> ArticleMetadata:
    return ArticleMetadata(
        title=article.title,
        author=article.author,
        published_date=article.published_date,
        price=article.price,
        slug=article.slug,
    )

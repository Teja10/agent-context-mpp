from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.db import get_article_by_slug, list_article_metadata
from app.models import ArticleMetadata
from app.state import AppState, get_state

router = APIRouter()


@router.get("/articles")
def get_articles(
    state: Annotated[AppState, Depends(get_state)],
) -> list[ArticleMetadata]:
    """Return public metadata for all stored articles."""
    return list_article_metadata(state.engine)


@router.get("/articles/{slug}")
def get_article(
    slug: str,
    state: Annotated[AppState, Depends(get_state)],
) -> ArticleMetadata:
    """Return public metadata for one stored article."""
    article = get_article_by_slug(state.engine, slug)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return article.metadata

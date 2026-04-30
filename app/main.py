from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.articles import ARTICLES_DIR, load_articles
from app.config import Settings
from app.routes import articles, health


def _initialize_database() -> None:
    pass


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Load startup resources before serving requests."""
    settings = Settings()
    settings.validate_mainnet_safety()
    articles.set_articles(load_articles(ARTICLES_DIR))
    _initialize_database()
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)
app.include_router(health.router)
app.include_router(articles.router)

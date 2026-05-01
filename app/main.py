from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.articles import ARTICLES_DIR, load_articles
from app.config import Settings
from app.db import initialize_database
from app.mpp_setup import create_mpp
from app.routes import articles, context, health


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Load startup resources before serving requests."""
    settings = Settings()
    settings.validate_mainnet_safety()
    loaded_articles = load_articles(ARTICLES_DIR)
    initialize_database(settings.database_path)
    articles.set_articles(loaded_articles)
    context.set_context(
        loaded_articles,
        create_mpp(settings),
        settings.database_path,
        settings.pathusd_address,
        settings.tempo_network,
    )
    yield


app = FastAPI(title="Thoth API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)
app.include_router(health.router)
app.include_router(articles.router)
app.include_router(context.router)

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings
from app.db import create_database_engine, verify_database
from app.mpp_setup import create_mpp
from app.routes import articles, context, health


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Load startup resources before serving requests."""
    settings = Settings()
    settings.validate_mainnet_safety()
    engine = create_database_engine(settings.database_url)
    verify_database(engine)
    articles.set_engine(engine)
    context.set_context(
        engine,
        create_mpp(settings),
        settings.pathusd_address,
        settings.tempo_network,
    )
    try:
        yield
    finally:
        engine.dispose()


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

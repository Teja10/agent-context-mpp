from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings
from app.db.queries import create_database_engine, verify_database
from app.mpp_setup import create_mpp
from app.routes import articles, context, health
from app.state import AppState


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Load startup resources before serving requests."""
    settings = Settings()
    settings.validate_mainnet_safety()
    engine = create_database_engine(settings.database_url)
    verify_database(engine)
    app.state.ctx = AppState(
        engine=engine,
        mpp=create_mpp(settings),
        pathusd_address=settings.pathusd_address,
        tempo_network=settings.tempo_network,
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

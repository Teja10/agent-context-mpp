from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings
from app.db.queries import create_database_engine, verify_database
from app.keystore import Keystore
from app.mpp_setup import create_mpp
from app.routes import articles, auth, context, health, publishers, subscriptions
from app.state import ActivationCache, AppState
from app.tempo_keychain import LiveKeychain


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
        keystore=Keystore(settings.subscription_keystore_key),
        keychain=LiveKeychain(rpc_url=settings.rpc_url, chain_id=settings.chain_id),
        activation_cache=ActivationCache(),
    )
    try:
        yield
    finally:
        engine.dispose()


app = FastAPI(title="Thoth API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)
app.include_router(health.router)
app.include_router(articles.router)
app.include_router(context.router)
app.include_router(auth.router)
app.include_router(publishers.router)
app.include_router(subscriptions.router)

"""Application state initialized during lifespan and injected into routes."""

from dataclasses import dataclass
from typing import cast

from fastapi import Request
from mpp.server.mpp import Mpp
from sqlalchemy.engine import Engine


@dataclass(frozen=True)
class AppState:
    """Startup-initialized resources shared across all routes."""

    engine: Engine
    mpp: Mpp
    pathusd_address: str
    tempo_network: str


def get_state(request: Request) -> AppState:
    """FastAPI dependency that returns the application state."""
    return cast(AppState, request.app.state.ctx)

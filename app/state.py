"""Application state initialized during lifespan and injected into routes."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
from typing import cast
from uuid import UUID

from fastapi import Request
from mpp.server.mpp import Mpp
from sqlalchemy.engine import Engine

from app.keystore import Keystore
from app.tempo_keychain import Keychain


@dataclass(frozen=True)
class PendingActivation:
    """Server-side state for an in-flight subscription signup."""

    wallet_address: str
    publisher_id: UUID
    key_id: str
    access_key_private_key: str
    monthly_price_str: str
    expiry: datetime
    period_seconds: int
    recipient: str
    currency: str
    expires_at: datetime


@dataclass
class ActivationCache:
    """In-memory TTL cache for pending subscription activations."""

    _entries: dict[str, PendingActivation] = field(default_factory=lambda: {})
    _lock: Lock = field(default_factory=Lock)

    def put(self, token: str, activation: PendingActivation) -> None:
        """Store a pending activation under its session token."""
        with self._lock:
            self._entries[token] = activation

    def consume(self, token: str) -> PendingActivation | None:
        """Pop and return a pending activation if it exists and is not expired."""
        now = datetime.now(UTC)
        with self._lock:
            entry = self._entries.pop(token, None)
            self._sweep_locked(now)
        if entry is None or entry.expires_at <= now:
            return None
        return entry

    def _sweep_locked(self, now: datetime) -> None:
        expired = [
            token for token, entry in self._entries.items() if entry.expires_at <= now
        ]
        for token in expired:
            del self._entries[token]


@dataclass(frozen=True)
class AppState:
    """Startup-initialized resources shared across all routes."""

    engine: Engine
    mpp: Mpp
    pathusd_address: str
    tempo_network: str
    keystore: Keystore
    keychain: Keychain
    activation_cache: ActivationCache


def get_state(request: Request) -> AppState:
    """FastAPI dependency that returns the application state."""
    return cast(AppState, request.app.state.ctx)

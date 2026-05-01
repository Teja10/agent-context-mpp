"""Publisher CRUD endpoints with wallet principal ownership."""

from decimal import Decimal
from typing import Annotated, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from app.auth import WalletPrincipal, require_wallet_principal
from app.db.queries import (
    create_publisher,
    get_publisher_by_handle,
    update_publisher,
)
from app.db.records import PublisherRecord
from app.state import AppState, get_state

router = APIRouter()


class CreatePublisher(BaseModel):
    """Request body for creating a publisher."""

    model_config = ConfigDict(extra="forbid")

    handle: str
    display_name: str
    description: str
    recipient_address: str
    default_article_price: Decimal
    default_subscription_price: Decimal


class PatchPublisher(BaseModel):
    """Request body for updating a publisher."""

    model_config = ConfigDict(extra="forbid")

    display_name: Optional[str] = None
    description: Optional[str] = None
    recipient_address: Optional[str] = None
    status: Optional[str] = None
    default_article_price: Optional[Decimal] = None
    default_subscription_price: Optional[Decimal] = None


def _publisher_dict(publisher: PublisherRecord) -> dict[str, object]:
    """Serialize a PublisherRecord to a JSON-safe dict."""
    return {
        "id": str(publisher.id),
        "handle": publisher.handle,
        "display_name": publisher.display_name,
        "owner_address": publisher.owner_address,
        "description": publisher.description,
        "status": publisher.status,
        "recipient_address": publisher.recipient_address,
        "default_article_price": str(publisher.default_article_price),
        "default_subscription_price": str(publisher.default_subscription_price),
    }


@router.post("/publishers", status_code=201)
def create_publisher_route(
    body: CreatePublisher,
    state: Annotated[AppState, Depends(get_state)],
    principal: Annotated[WalletPrincipal, Depends(require_wallet_principal)],
) -> dict[str, object]:
    """Create a new publisher. Requires wallet authentication.

    Args:
        body: Publisher creation fields.
        state: Application state.
        principal: Authenticated wallet principal.

    Returns:
        Created publisher fields.

    Raises:
        HTTPException: 409 if handle already taken.
    """
    publisher = create_publisher(
        state.engine,
        publisher_id=uuid4(),
        handle=body.handle,
        display_name=body.display_name,
        description=body.description,
        owner_address=principal.wallet_address,
        recipient_address=body.recipient_address.lower(),
        default_article_price=body.default_article_price,
        default_subscription_price=body.default_subscription_price,
    )
    if publisher is None:
        raise HTTPException(status_code=409, detail="Handle already taken")
    return _publisher_dict(publisher)


@router.get("/publishers/{handle}")
def get_publisher_route(
    handle: str,
    state: Annotated[AppState, Depends(get_state)],
) -> dict[str, object]:
    """Get a publisher by handle. Public endpoint.

    Args:
        handle: Publisher handle.
        state: Application state.

    Returns:
        Publisher fields.

    Raises:
        HTTPException: 404 if publisher not found.
    """
    publisher = get_publisher_by_handle(state.engine, handle)
    if publisher is None:
        raise HTTPException(status_code=404, detail="Publisher not found")
    return _publisher_dict(publisher)


@router.patch("/publishers/{handle}")
def patch_publisher(
    handle: str,
    body: PatchPublisher,
    state: Annotated[AppState, Depends(get_state)],
    principal: Annotated[WalletPrincipal, Depends(require_wallet_principal)],
) -> dict[str, object]:
    """Update publisher fields. Requires wallet ownership.

    Args:
        handle: Publisher handle to update.
        body: Request body with optional fields to update.
        state: Application state.
        principal: Authenticated wallet principal.

    Returns:
        Updated publisher fields.

    Raises:
        HTTPException: 404 if publisher not found, 403 if wallet mismatch,
            422 if no fields provided.
    """
    values = body.model_dump(exclude_none=True)
    if len(values) == 0:
        raise HTTPException(status_code=422, detail="No fields to update")
    publisher = get_publisher_by_handle(state.engine, handle)
    if publisher is None:
        raise HTTPException(status_code=404, detail="Publisher not found")
    if principal.wallet_address != publisher.owner_address:
        raise HTTPException(status_code=403, detail="Wallet does not own publisher")
    update_publisher(state.engine, handle, values)
    updated = get_publisher_by_handle(state.engine, handle)
    if updated is None:
        raise HTTPException(status_code=404, detail="Publisher not found")
    return _publisher_dict(updated)

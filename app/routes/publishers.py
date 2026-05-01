"""Publisher mutation endpoints requiring wallet principal auth."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from app.auth import WalletPrincipal, require_wallet_principal
from app.db.queries import get_publisher_by_handle, update_publisher_display_name
from app.state import AppState, get_state

router = APIRouter()


class UpdatePublisher(BaseModel):
    """Request body for updating a publisher."""

    model_config = ConfigDict(extra="forbid")

    display_name: str


@router.patch("/publishers/{handle}")
def patch_publisher(
    handle: str,
    body: UpdatePublisher,
    state: Annotated[AppState, Depends(get_state)],
    principal: Annotated[WalletPrincipal, Depends(require_wallet_principal)],
) -> dict[str, str]:
    """Update publisher display name. Requires wallet ownership.

    Args:
        handle: Publisher handle to update.
        body: Request body with new display_name.
        state: Application state.
        principal: Authenticated wallet principal.

    Returns:
        Updated publisher handle and display_name.

    Raises:
        HTTPException: 404 if publisher not found, 403 if wallet mismatch.
    """
    publisher = get_publisher_by_handle(state.engine, handle)
    if publisher is None:
        raise HTTPException(status_code=404, detail="Publisher not found")
    if principal.wallet_address != publisher.recipient_address.lower():
        raise HTTPException(status_code=403, detail="Wallet does not own publisher")
    update_publisher_display_name(state.engine, handle, body.display_name)
    return {"handle": handle, "display_name": body.display_name}

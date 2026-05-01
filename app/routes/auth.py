"""Authentication challenge endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends
from mpp import Challenge

from app.state import AppState, get_state

router = APIRouter()


@router.post("/auth/challenge")
def create_challenge(
    state: Annotated[AppState, Depends(get_state)],
) -> dict[str, str]:
    """Issue an HMAC-bound nonce for wallet signature authentication.

    Returns:
        JSON with ``challenge`` (the nonce to sign) and ``realm``.
    """
    challenge = Challenge.create(
        secret_key=state.mpp.secret_key,
        realm=state.mpp.realm,
        method="tempo",
        intent="auth",
        request={},
    )
    return {"challenge": challenge.id, "realm": state.mpp.realm}

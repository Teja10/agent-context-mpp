from mpp.methods.tempo import ChargeIntent, tempo
from mpp.server.mpp import Mpp

from app.config import Settings


def create_mpp(settings: Settings) -> Mpp:
    """Create the configured MPP payment handler."""
    return Mpp.create(
        method=tempo(
            intents={
                "charge": ChargeIntent(
                    chain_id=settings.chain_id,
                    rpc_url=settings.rpc_url,
                )
            },
            chain_id=settings.chain_id,
            rpc_url=settings.rpc_url,
            currency=settings.payment_currency_address,
            recipient=settings.publisher_recipient,
        ),
        realm=settings.mpp_realm,
        secret_key=settings.mpp_secret_key,
    )

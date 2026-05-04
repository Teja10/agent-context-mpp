"""Daily subscription renewer.

Selects ``subscription_authorizations`` whose latest period_end is within a
24h window, decrypts each held access key, signs and submits a fresh
``transferWithMemo`` against the on-chain ``TokenLimit`` window, and inserts
the new period row on success. Mirrors Stripe Smart Retries: 3 attempts per
period with an 8h gap, then ``renewal_failed``.

Idempotent: rerunning is safe because the unique
``(wallet, publisher, period_start, period_end)`` constraint and unique
``payment_reference`` guard against duplicate inserts. Run via the platform
scheduler (Render Cron / k8s CronJob).
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from app.config import Settings
from app.db.queries import (
    clear_renewal_attempt,
    create_database_engine,
    get_authorization_with_key,
    get_publisher_by_id,
    insert_subscription_period,
    mark_authorization_status,
    record_renewal_attempt,
    select_due_renewals,
    verify_database,
)
from app.db.records import DueRenewal, SubscriptionPeriod
from app.keystore import Keystore
from app.tempo_keychain import (
    Keychain,
    LiveKeychain,
    PeriodChargeError,
    derive_subscription_memo,
    receipt_payload,
)

EXPIRY_BUFFER_SECONDS = 24 * 60 * 60
RETRY_GAP_SECONDS = 8 * 60 * 60
MAX_RENEWAL_ATTEMPTS = 3
PERIOD_SECONDS_30_DAYS = 30 * 24 * 60 * 60

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RenewalSummary:
    """Per-run counters for the renewer."""

    succeeded: list[str]
    retried: list[str]
    failed: list[str]


async def renew_due_subscriptions(
    settings: Settings,
    keystore: Keystore,
    keychain: Keychain,
) -> RenewalSummary:
    """Run one renewal pass over all due authorizations."""
    settings.validate_mainnet_safety()
    engine = create_database_engine(settings.database_url)
    verify_database(engine)
    succeeded: list[str] = []
    retried: list[str] = []
    failed: list[str] = []
    try:
        now = datetime.now(UTC)
        due = select_due_renewals(
            engine,
            now,
            expiry_buffer_seconds=EXPIRY_BUFFER_SECONDS,
            retry_gap_seconds=RETRY_GAP_SECONDS,
            max_attempts=MAX_RENEWAL_ATTEMPTS,
        )
        for renewal in due:
            outcome = await _renew_one(
                settings,
                keystore,
                keychain,
                renewal,
            )
            if outcome == "succeeded":
                succeeded.append(str(renewal.authorization_id))
            elif outcome == "failed":
                failed.append(str(renewal.authorization_id))
            else:
                retried.append(str(renewal.authorization_id))
    finally:
        engine.dispose()
    return RenewalSummary(succeeded=succeeded, retried=retried, failed=failed)


async def _renew_one(
    settings: Settings,
    keystore: Keystore,
    keychain: Keychain,
    renewal: DueRenewal,
) -> str:
    """Charge one period for a due renewal. Returns terminal status."""
    engine = create_database_engine(settings.database_url)
    try:
        loaded = get_authorization_with_key(engine, renewal.authorization_id)
        if loaded is None:
            logger.error(
                "renewer_authorization_missing authorization_id=%s",
                renewal.authorization_id,
            )
            mark_authorization_status(
                engine, renewal.authorization_id, "renewal_failed"
            )
            return "failed"
        authorization, ciphertext = loaded
        publisher = get_publisher_by_id(engine, authorization.publisher_id)
        if publisher is None:
            logger.error(
                "renewer_publisher_missing publisher_id=%s",
                authorization.publisher_id,
            )
            mark_authorization_status(
                engine, renewal.authorization_id, "renewal_failed"
            )
            return "failed"
        ak_priv_bytes = keystore.decrypt(ciphertext)
        ak_priv_hex = "0x" + ak_priv_bytes.hex()
        period_start = renewal.last_period_end
        memo = derive_subscription_memo(
            authorization.publisher_id, authorization.wallet_address, period_start
        )
        try:
            charge = await keychain.submit_period_charge(
                access_key_private_key=ak_priv_hex,
                wallet_address=authorization.wallet_address,
                recipient=publisher.recipient_address,
                currency=settings.pathusd_address,
                monthly_price=publisher.default_subscription_price,
                memo=memo,
            )
        except PeriodChargeError as err:
            attempts = record_renewal_attempt(
                engine, renewal.authorization_id, period_start, str(err)
            )
            if attempts >= MAX_RENEWAL_ATTEMPTS:
                mark_authorization_status(
                    engine, renewal.authorization_id, "renewal_failed"
                )
                logger.error(
                    "renewer_failed authorization_id=%s attempts=%s reason=%s",
                    renewal.authorization_id,
                    attempts,
                    err,
                )
                return "failed"
            logger.warning(
                "renewer_retry authorization_id=%s attempts=%s reason=%s",
                renewal.authorization_id,
                attempts,
                err,
            )
            return "retried"
        period_amount = publisher.default_subscription_price
        period_end = period_start + timedelta(seconds=PERIOD_SECONDS_30_DAYS)
        insert_subscription_period(
            engine,
            SubscriptionPeriod(
                id=uuid4(),
                wallet_address=authorization.wallet_address,
                publisher_id=authorization.publisher_id,
                period_start=period_start,
                period_end=period_end,
                payment_reference=charge.payment_reference,
                amount=Decimal(period_amount),
                currency=settings.pathusd_address,
                network=settings.tempo_network,
                receipt=receipt_payload(
                    tx_hash=charge.payment_reference,
                    block_number=charge.block_number,
                    network=settings.tempo_network,
                    charged_at=datetime.now(UTC),
                ),
            ),
        )
        clear_renewal_attempt(engine, renewal.authorization_id, period_start)
        logger.info(
            "renewer_succeeded authorization_id=%s tx=%s",
            renewal.authorization_id,
            charge.payment_reference,
        )
        return "succeeded"
    finally:
        engine.dispose()


def _build_runtime() -> tuple[Settings, Keystore, Keychain]:
    settings = Settings()
    keystore = Keystore(settings.subscription_keystore_key)
    keychain = LiveKeychain(rpc_url=settings.rpc_url, chain_id=settings.chain_id)
    return settings, keystore, keychain


def main() -> None:
    """Entrypoint used by Render Cron / k8s CronJob."""
    logging.basicConfig(level=logging.INFO)
    settings, keystore, keychain = _build_runtime()
    summary = asyncio.run(renew_due_subscriptions(settings, keystore, keychain))
    logger.info(
        "renewer_summary succeeded=%s retried=%s failed=%s",
        len(summary.succeeded),
        len(summary.retried),
        len(summary.failed),
    )


if __name__ == "__main__":
    main()

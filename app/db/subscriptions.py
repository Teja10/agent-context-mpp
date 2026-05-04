"""Subscription authorization, period, and renewal-attempt query functions."""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import and_, desc, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine, RowMapping

from app.db.queries import upsert_wallet_principal
from app.db.records import DueRenewal, SubscriptionAuthorization, SubscriptionPeriod
from app.db.schema import (
    subscription_authorization_keys,
    subscription_authorizations,
    subscription_renewal_attempts,
    subscriptions,
)


def insert_authorization_with_key(
    engine: Engine,
    *,
    wallet_address: str,
    publisher_id: UUID,
    key_id: str,
    expiry: datetime,
    authorize_tx_hash: str,
    encrypted_key: bytes,
) -> SubscriptionAuthorization:
    """Insert a new active authorization and its encrypted access key atomically.

    Raises:
        RuntimeError: If the wallet already has an active authorization for
            the publisher or the authorize_tx_hash collides.
    """
    upsert_wallet_principal(engine, wallet_address)
    authorization_id = uuid4()
    with engine.begin() as connection:
        inserted = connection.execute(
            insert(subscription_authorizations)
            .values(
                id=authorization_id,
                wallet_address=wallet_address,
                publisher_id=publisher_id,
                key_id=key_id,
                expiry=expiry,
                status="active",
                authorize_tx_hash=authorize_tx_hash,
                created_at=text("now()"),
            )
            .on_conflict_do_nothing()
            .returning(subscription_authorizations.c.id)
        ).scalar_one_or_none()
        if inserted is None:
            raise RuntimeError(
                "Authorization already exists for this wallet/publisher or tx hash"
            )
        connection.execute(
            insert(subscription_authorization_keys).values(
                authorization_id=authorization_id,
                ciphertext=encrypted_key,
                created_at=text("now()"),
            )
        )
    return SubscriptionAuthorization(
        id=authorization_id,
        wallet_address=wallet_address,
        publisher_id=publisher_id,
        key_id=key_id,
        expiry=expiry,
        status="active",
        authorize_tx_hash=authorize_tx_hash,
    )


def get_active_authorization(
    engine: Engine, wallet_address: str, publisher_id: UUID
) -> Optional[SubscriptionAuthorization]:
    """Return the wallet's active authorization for a publisher, if any."""
    with engine.connect() as connection:
        row = (
            connection.execute(
                select(subscription_authorizations)
                .where(subscription_authorizations.c.wallet_address == wallet_address)
                .where(subscription_authorizations.c.publisher_id == publisher_id)
                .where(subscription_authorizations.c.status == "active")
            )
            .mappings()
            .one_or_none()
        )
    if row is None:
        return None
    return _subscription_authorization(row)


def get_authorization_with_key(
    engine: Engine, authorization_id: UUID
) -> Optional[tuple[SubscriptionAuthorization, bytes]]:
    """Return the authorization and its ciphertext for the renewer."""
    with engine.connect() as connection:
        row = (
            connection.execute(
                select(
                    subscription_authorizations,
                    subscription_authorization_keys.c.ciphertext,
                )
                .select_from(
                    subscription_authorizations.join(
                        subscription_authorization_keys,
                        subscription_authorizations.c.id
                        == subscription_authorization_keys.c.authorization_id,
                    )
                )
                .where(subscription_authorizations.c.id == authorization_id)
            )
            .mappings()
            .one_or_none()
        )
    if row is None:
        return None
    return _subscription_authorization(row), bytes(row["ciphertext"])


def mark_authorization_status(
    engine: Engine, authorization_id: UUID, status: str
) -> None:
    """Update authorization status (cancelled/revoked/expired/renewal_failed)."""
    with engine.begin() as connection:
        connection.execute(
            update(subscription_authorizations)
            .where(subscription_authorizations.c.id == authorization_id)
            .values(status=status)
        )


def insert_subscription_period(
    engine: Engine, period: SubscriptionPeriod
) -> SubscriptionPeriod:
    """Persist a verified subscription period receipt.

    Raises:
        RuntimeError: If the (wallet, publisher, period) range or the
            payment_reference already exists.
    """
    upsert_wallet_principal(engine, period.wallet_address)
    with engine.begin() as connection:
        inserted = connection.execute(
            insert(subscriptions)
            .values(
                id=period.id,
                wallet_address=period.wallet_address,
                publisher_id=period.publisher_id,
                period_start=period.period_start,
                period_end=period.period_end,
                payment_reference=period.payment_reference,
                amount=period.amount,
                currency=period.currency,
                network=period.network,
                receipt=period.receipt,
                created_at=text("now()"),
            )
            .on_conflict_do_nothing()
            .returning(subscriptions.c.id)
        ).scalar_one_or_none()
        if inserted is None:
            raise RuntimeError(
                "Subscription period already recorded for this window or reference"
            )
    return period


def get_active_subscription(
    engine: Engine,
    wallet_address: str,
    publisher_id: UUID,
    now: datetime,
) -> Optional[SubscriptionPeriod]:
    """Return the wallet's active subscription period for a publisher, if any."""
    with engine.connect() as connection:
        row = (
            connection.execute(
                select(subscriptions)
                .where(subscriptions.c.wallet_address == wallet_address)
                .where(subscriptions.c.publisher_id == publisher_id)
                .where(subscriptions.c.period_start <= now)
                .where(subscriptions.c.period_end > now)
            )
            .mappings()
            .one_or_none()
        )
    if row is None:
        return None
    return _subscription_period(row)


def get_latest_subscription_period(
    engine: Engine, wallet_address: str, publisher_id: UUID
) -> Optional[SubscriptionPeriod]:
    """Return the most recent subscription period for a wallet/publisher."""
    with engine.connect() as connection:
        row = (
            connection.execute(
                select(subscriptions)
                .where(subscriptions.c.wallet_address == wallet_address)
                .where(subscriptions.c.publisher_id == publisher_id)
                .order_by(desc(subscriptions.c.period_end))
                .limit(1)
            )
            .mappings()
            .one_or_none()
        )
    if row is None:
        return None
    return _subscription_period(row)


def select_due_renewals(
    engine: Engine,
    now: datetime,
    *,
    expiry_buffer_seconds: int,
    retry_gap_seconds: int,
    max_attempts: int,
) -> list[DueRenewal]:
    """Return authorizations whose latest period is ending and ready for charge."""
    sql = text("""
        SELECT a.id AS authorization_id,
               a.wallet_address,
               a.publisher_id,
               a.key_id,
               a.expiry,
               latest.period_end AS last_period_end,
               COALESCE(att.attempts, 0) AS attempts,
               att.last_attempt_at AS last_attempt_at
        FROM subscription_authorizations a
        JOIN LATERAL (
            SELECT period_end FROM subscriptions s
            WHERE s.wallet_address = a.wallet_address
              AND s.publisher_id = a.publisher_id
            ORDER BY period_end DESC
            LIMIT 1
        ) latest ON TRUE
        LEFT JOIN subscription_renewal_attempts att
          ON att.authorization_id = a.id
         AND att.period_start = latest.period_end
        WHERE a.status = 'active'
          AND a.expiry > :now + (:expiry_buffer || ' seconds')::interval
          AND latest.period_end < :now + (:expiry_buffer || ' seconds')::interval
          AND COALESCE(att.attempts, 0) < :max_attempts
          AND (att.last_attempt_at IS NULL
               OR att.last_attempt_at <
                  :now - (:retry_gap || ' seconds')::interval)
    """)
    with engine.connect() as connection:
        rows = connection.execute(
            sql,
            {
                "now": now,
                "expiry_buffer": expiry_buffer_seconds,
                "retry_gap": retry_gap_seconds,
                "max_attempts": max_attempts,
            },
        ).mappings()
        return [
            DueRenewal(
                authorization_id=row["authorization_id"],
                wallet_address=row["wallet_address"],
                publisher_id=row["publisher_id"],
                key_id=row["key_id"],
                expiry=row["expiry"],
                last_period_end=row["last_period_end"],
                attempts=row["attempts"],
                last_attempt_at=row["last_attempt_at"],
            )
            for row in rows
        ]


def record_renewal_attempt(
    engine: Engine,
    authorization_id: UUID,
    period_start: datetime,
    error: str,
) -> int:
    """Increment the renewal-attempt counter for a (auth, period) pair."""
    with engine.begin() as connection:
        attempts = connection.execute(
            insert(subscription_renewal_attempts)
            .values(
                authorization_id=authorization_id,
                period_start=period_start,
                attempts=1,
                last_attempt_at=text("now()"),
                last_error=error,
            )
            .on_conflict_do_update(
                index_elements=[
                    subscription_renewal_attempts.c.authorization_id,
                    subscription_renewal_attempts.c.period_start,
                ],
                set_={
                    "attempts": subscription_renewal_attempts.c.attempts + 1,
                    "last_attempt_at": text("now()"),
                    "last_error": error,
                },
            )
            .returning(subscription_renewal_attempts.c.attempts)
        ).scalar_one()
    return int(attempts)


def clear_renewal_attempt(
    engine: Engine, authorization_id: UUID, period_start: datetime
) -> None:
    """Drop the attempt-counter row after a successful renewal."""
    with engine.begin() as connection:
        connection.execute(
            subscription_renewal_attempts.delete().where(
                and_(
                    subscription_renewal_attempts.c.authorization_id
                    == authorization_id,
                    subscription_renewal_attempts.c.period_start == period_start,
                )
            )
        )


def _subscription_authorization(row: RowMapping) -> SubscriptionAuthorization:
    return SubscriptionAuthorization(
        id=row["id"],
        wallet_address=row["wallet_address"],
        publisher_id=row["publisher_id"],
        key_id=row["key_id"],
        expiry=row["expiry"],
        status=row["status"],
        authorize_tx_hash=row["authorize_tx_hash"],
    )


def _subscription_period(row: RowMapping) -> SubscriptionPeriod:
    return SubscriptionPeriod(
        id=row["id"],
        wallet_address=row["wallet_address"],
        publisher_id=row["publisher_id"],
        period_start=row["period_start"],
        period_end=row["period_end"],
        payment_reference=row["payment_reference"],
        amount=row["amount"],
        currency=row["currency"],
        network=row["network"],
        receipt=dict(row["receipt"]),
    )

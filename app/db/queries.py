"""Database query and engine functions."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import and_, create_engine, desc, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine, RowMapping

from app.db.records import (
    ArticleRecord,
    DueRenewal,
    OneTimePurchase,
    PublisherRecord,
    SubscriptionAuthorization,
    SubscriptionPeriod,
)
from app.db.schema import (
    articles,
    metadata,
    one_time_purchases,
    publishers,
    subscription_authorization_keys,
    subscription_authorizations,
    subscription_renewal_attempts,
    subscriptions,
    wallet_principals,
)
from app.models import ArticleMetadata


def create_database_engine(database_url: str) -> Engine:
    """Create a Postgres SQLAlchemy engine from an explicit URL."""
    return create_engine(database_url)


def verify_database(engine: Engine) -> None:
    """Verify connectivity and that migrations have created expected tables."""
    expected_tables = set(metadata.tables.keys())
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                select table_name
                from information_schema.tables
                where table_schema = 'public'
                """
            )
        )
        existing_tables = {str(row["table_name"]) for row in rows.mappings()}
    missing_tables = expected_tables - existing_tables
    if missing_tables:
        raise RuntimeError(f"Database is missing tables: {missing_tables}")


def list_article_metadata(engine: Engine) -> list[ArticleMetadata]:
    """Return public metadata for all published articles ordered by slug."""
    with engine.connect() as connection:
        rows = connection.execute(
            select(
                articles.c.title,
                articles.c.author,
                articles.c.published_at,
                articles.c.price,
                articles.c.slug,
            )
            .where(articles.c.status == "published")
            .order_by(articles.c.slug)
        )
        return [
            ArticleMetadata(
                title=row["title"],
                author=row["author"],
                published_date=row["published_at"],
                price=str(row["price"]),
                slug=row["slug"],
            )
            for row in rows.mappings()
        ]


def list_articles(engine: Engine) -> list[ArticleRecord]:
    """Return all articles ordered by slug, joined with their publishers."""
    with engine.connect() as connection:
        rows = connection.execute(
            select(
                articles,
                publishers.c.recipient_address.label("publisher_recipient_address"),
            )
            .select_from(
                articles.join(publishers, articles.c.publisher_id == publishers.c.id)
            )
            .order_by(articles.c.slug)
        )
        return [_article_record(row) for row in rows.mappings()]


def get_article_by_slug(engine: Engine, slug: str) -> Optional[ArticleRecord]:
    """Return one published article by its slug, joined with its publisher."""
    with engine.connect() as connection:
        row = (
            connection.execute(
                select(
                    articles,
                    publishers.c.recipient_address.label("publisher_recipient_address"),
                )
                .select_from(
                    articles.join(
                        publishers, articles.c.publisher_id == publishers.c.id
                    )
                )
                .where(articles.c.slug == slug)
                .where(articles.c.status == "published")
            )
            .mappings()
            .one_or_none()
        )
    if row is None:
        return None
    return _article_record(row)


def get_article_by_slug_for_owner(engine: Engine, slug: str) -> Optional[ArticleRecord]:
    """Return one article by slug regardless of status, joined with its publisher.

    Args:
        engine: SQLAlchemy engine.
        slug: Article slug.

    Returns:
        ArticleRecord if found, None otherwise.
    """
    with engine.connect() as connection:
        row = (
            connection.execute(
                select(
                    articles,
                    publishers.c.recipient_address.label("publisher_recipient_address"),
                )
                .select_from(
                    articles.join(
                        publishers, articles.c.publisher_id == publishers.c.id
                    )
                )
                .where(articles.c.slug == slug)
            )
            .mappings()
            .one_or_none()
        )
    if row is None:
        return None
    return _article_record(row)


def upsert_wallet_principal(engine: Engine, address: str) -> None:
    """Insert a wallet principal if it does not already exist.

    Args:
        engine: SQLAlchemy engine.
        address: Lowercase wallet address.
    """
    with engine.begin() as connection:
        connection.execute(
            insert(wallet_principals)
            .values(wallet_address=address, created_at=text("now()"))
            .on_conflict_do_nothing(index_elements=[wallet_principals.c.wallet_address])
        )


def insert_one_time_purchase(
    engine: Engine,
    purchase: OneTimePurchase,
    article_id: UUID,
) -> OneTimePurchase:
    """Persist a wallet principal and one-time purchase."""
    upsert_wallet_principal(engine, purchase.wallet_address)
    with engine.begin() as connection:
        result = connection.execute(
            insert(one_time_purchases)
            .values(
                id=text("gen_random_uuid()"),
                wallet_address=purchase.wallet_address,
                article_id=article_id,
                payment_reference=purchase.payment_reference,
                amount=purchase.amount,
                currency=purchase.currency,
                network=purchase.network,
                recipient_wallet=purchase.recipient_wallet,
                receipt=purchase.receipt,
                created_at=text("now()"),
            )
            .on_conflict_do_nothing()
        )
    if result.rowcount == 1:
        return purchase
    existing_purchase = lookup_purchase_by_payment_reference(
        engine, purchase.payment_reference
    )
    if existing_purchase is None:
        raise RuntimeError("Wallet already purchased this article")
    if existing_purchase != purchase:
        raise RuntimeError("Payment reference is bound to different purchase details")
    return existing_purchase


def get_one_time_purchase_for_article(
    engine: Engine,
    wallet_address: str,
    article_id: UUID,
) -> Optional[OneTimePurchase]:
    """Return the wallet's existing one-time purchase for an article, if any.

    The unique ``(wallet_address, article_id)`` constraint guarantees at most
    one row matches, so this lookup encodes "has this wallet ever paid for
    this article?" — the persistent-PPV entitlement.
    """
    with engine.connect() as connection:
        row = (
            connection.execute(
                select(
                    articles.c.slug.label("article_slug"),
                    one_time_purchases.c.wallet_address,
                    one_time_purchases.c.payment_reference,
                    one_time_purchases.c.amount,
                    one_time_purchases.c.currency,
                    one_time_purchases.c.network,
                    one_time_purchases.c.recipient_wallet,
                    one_time_purchases.c.receipt,
                )
                .select_from(
                    one_time_purchases.join(
                        articles, one_time_purchases.c.article_id == articles.c.id
                    )
                )
                .where(one_time_purchases.c.wallet_address == wallet_address)
                .where(one_time_purchases.c.article_id == article_id)
            )
            .mappings()
            .one_or_none()
        )
    if row is None:
        return None
    return _one_time_purchase(row)


def lookup_purchase_by_payment_reference(
    engine: Engine,
    payment_reference: str,
) -> Optional[OneTimePurchase]:
    """Return the purchase stored for a payment reference."""
    with engine.connect() as connection:
        row = (
            connection.execute(
                select(
                    articles.c.slug.label("article_slug"),
                    one_time_purchases.c.wallet_address,
                    one_time_purchases.c.payment_reference,
                    one_time_purchases.c.amount,
                    one_time_purchases.c.currency,
                    one_time_purchases.c.network,
                    one_time_purchases.c.recipient_wallet,
                    one_time_purchases.c.receipt,
                )
                .select_from(
                    one_time_purchases.join(
                        articles,
                        one_time_purchases.c.article_id == articles.c.id,
                    )
                )
                .where(one_time_purchases.c.payment_reference == payment_reference)
            )
            .mappings()
            .one_or_none()
        )
    if row is None:
        return None
    return _one_time_purchase(row)


def _article_record(row: RowMapping) -> ArticleRecord:
    return ArticleRecord(
        id=row["id"],
        publisher_id=row["publisher_id"],
        title=row["title"],
        status=row["status"],
        author=row["author"],
        published_date=row["published_at"],
        price=row["price"],
        license=row["license"],
        summary=row["summary"],
        tags=list(row["tags"]) if row["tags"] is not None else None,
        key_claims=list(row["key_claims"]) if row["key_claims"] is not None else None,
        allowed_excerpts=(
            list(row["allowed_excerpts"])
            if row["allowed_excerpts"] is not None
            else None
        ),
        suggested_citation=row["suggested_citation"],
        slug=row["slug"],
        body=row["body"],
        publisher_recipient_address=row["publisher_recipient_address"],
    )


def insert_article(
    engine: Engine,
    article_id: UUID,
    publisher_id: UUID,
    slug: str,
    title: str,
    body: str,
    author: Optional[str],
    price: Optional[Decimal],
    license: Optional[str],
    summary: Optional[str],
    tags: Optional[list[str]],
    key_claims: Optional[list[str]],
    allowed_excerpts: Optional[list[str]],
    suggested_citation: Optional[str],
) -> Optional[ArticleRecord]:
    """Insert a draft article. Return None on (publisher_id, slug) conflict.

    Args:
        engine: SQLAlchemy engine.
        article_id: UUID for the new article.
        publisher_id: Publisher that owns the article.
        slug: URL slug.
        title: Article title.
        body: Markdown body text.
        author: Optional author name.
        price: Optional price.
        license: Optional license string.
        summary: Optional summary.
        tags: Optional list of tags.
        key_claims: Optional list of key claims.
        allowed_excerpts: Optional list of allowed excerpts.
        suggested_citation: Optional citation string.

    Returns:
        ArticleRecord if inserted, None if slug conflict.
    """
    with engine.begin() as connection:
        inserted_slug = connection.execute(
            insert(articles)
            .values(
                id=article_id,
                publisher_id=publisher_id,
                slug=slug,
                title=title,
                status="draft",
                author=author,
                price=price,
                license=license,
                summary=summary,
                tags=tags,
                key_claims=key_claims,
                allowed_excerpts=allowed_excerpts,
                suggested_citation=suggested_citation,
                body=body,
                created_at=text("now()"),
                updated_at=text("now()"),
            )
            .on_conflict_do_nothing(
                constraint="articles_publisher_slug_key",
            )
            .returning(articles.c.slug)
        ).scalar_one_or_none()
    if inserted_slug is None:
        return None
    return get_article_by_slug_for_owner(engine, inserted_slug)


def update_article(
    engine: Engine, slug: str, publisher_id: UUID, values: dict[str, object]
) -> None:
    """Update article fields by slug and publisher_id.

    Args:
        engine: SQLAlchemy engine.
        slug: Article slug.
        publisher_id: Publisher UUID (ownership filter).
        values: Column-value pairs to update.
    """
    values["updated_at"] = text("now()")
    with engine.begin() as connection:
        connection.execute(
            update(articles)
            .where(articles.c.slug == slug)
            .where(articles.c.publisher_id == publisher_id)
            .values(**values)
        )


def publish_article(engine: Engine, slug: str, publisher_id: UUID) -> None:
    """Set article status to published with current date.

    Args:
        engine: SQLAlchemy engine.
        slug: Article slug.
        publisher_id: Publisher UUID (ownership filter).
    """
    with engine.begin() as connection:
        connection.execute(
            update(articles)
            .where(articles.c.slug == slug)
            .where(articles.c.publisher_id == publisher_id)
            .values(
                status="published",
                published_at=date.today(),
                updated_at=text("now()"),
            )
        )


def create_publisher(
    engine: Engine,
    publisher_id: UUID,
    handle: str,
    display_name: str,
    description: str,
    owner_address: str,
    recipient_address: str,
    default_article_price: Decimal,
    default_subscription_price: Decimal,
) -> Optional[PublisherRecord]:
    """Insert a new publisher with on_conflict_do_nothing on handle.

    Args:
        engine: SQLAlchemy engine.
        publisher_id: UUID for the new publisher.
        handle: Unique publisher handle.
        display_name: Display name.
        description: Publisher description.
        owner_address: Wallet address of the owner.
        recipient_address: Payment recipient address.
        default_article_price: Default price for articles.
        default_subscription_price: Default price for subscriptions.

    Returns:
        PublisherRecord if inserted, None if handle conflict.
    """
    with engine.begin() as connection:
        row = connection.execute(
            insert(publishers)
            .values(
                id=publisher_id,
                handle=handle,
                display_name=display_name,
                owner_address=owner_address,
                description=description,
                status="active",
                recipient_address=recipient_address,
                default_article_price=default_article_price,
                default_subscription_price=default_subscription_price,
                created_at=text("now()"),
            )
            .on_conflict_do_nothing(index_elements=[publishers.c.handle])
            .returning(publishers.c.id)
        ).scalar_one_or_none()
    if row is None:
        return None
    return PublisherRecord(
        id=publisher_id,
        handle=handle,
        display_name=display_name,
        owner_address=owner_address,
        description=description,
        status="active",
        recipient_address=recipient_address,
        default_article_price=default_article_price,
        default_subscription_price=default_subscription_price,
    )


def get_publisher_by_handle(engine: Engine, handle: str) -> Optional[PublisherRecord]:
    """Return a publisher by its unique handle.

    Args:
        engine: SQLAlchemy engine.
        handle: Publisher handle.

    Returns:
        PublisherRecord if found, None otherwise.
    """
    with engine.connect() as connection:
        row = (
            connection.execute(select(publishers).where(publishers.c.handle == handle))
            .mappings()
            .one_or_none()
        )
    if row is None:
        return None
    return _publisher_record(row)


def get_publisher_by_id(
    engine: Engine, publisher_id: UUID
) -> Optional[PublisherRecord]:
    """Return a publisher by its primary key.

    Args:
        engine: SQLAlchemy engine.
        publisher_id: Publisher UUID.

    Returns:
        PublisherRecord if found, None otherwise.
    """
    with engine.connect() as connection:
        row = (
            connection.execute(
                select(publishers).where(publishers.c.id == publisher_id)
            )
            .mappings()
            .one_or_none()
        )
    if row is None:
        return None
    return _publisher_record(row)


def update_publisher(engine: Engine, handle: str, values: dict[str, object]) -> None:
    """Update publisher fields by handle.

    Args:
        engine: SQLAlchemy engine.
        handle: Publisher handle.
        values: Column-value pairs to update.
    """
    with engine.begin() as connection:
        connection.execute(
            update(publishers).where(publishers.c.handle == handle).values(**values)
        )


def _publisher_record(row: RowMapping) -> PublisherRecord:
    return PublisherRecord(
        id=row["id"],
        handle=row["handle"],
        display_name=row["display_name"],
        owner_address=row["owner_address"],
        description=row["description"],
        status=row["status"],
        recipient_address=row["recipient_address"],
        default_article_price=row["default_article_price"],
        default_subscription_price=row["default_subscription_price"],
    )


def _one_time_purchase(row: RowMapping) -> OneTimePurchase:
    return OneTimePurchase(
        article_slug=row["article_slug"],
        wallet_address=row["wallet_address"],
        payment_reference=row["payment_reference"],
        amount=row["amount"],
        currency=row["currency"],
        network=row["network"],
        recipient_wallet=row["recipient_wallet"],
        receipt=dict(row["receipt"]),
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

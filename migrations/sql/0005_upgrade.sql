ALTER TABLE subscriptions
    ALTER COLUMN period_start TYPE TIMESTAMPTZ USING period_start::timestamptz,
    ALTER COLUMN period_end TYPE TIMESTAMPTZ USING period_end::timestamptz;

CREATE TABLE subscription_authorizations (
    id UUID PRIMARY KEY,
    wallet_address TEXT NOT NULL
        REFERENCES wallet_principals (wallet_address),
    publisher_id UUID NOT NULL REFERENCES publishers (id),
    key_id TEXT NOT NULL,
    expiry TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL,
    authorize_tx_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT subscription_authorizations_status_valid
        CHECK (status IN ('active', 'cancelled', 'revoked', 'expired',
                          'renewal_failed')),
    CONSTRAINT subscription_authorizations_key_id_nonempty
        CHECK (key_id <> ''),
    CONSTRAINT subscription_authorizations_authorize_tx_hash_key
        UNIQUE (authorize_tx_hash)
);

CREATE UNIQUE INDEX subscription_authorizations_one_active
    ON subscription_authorizations (wallet_address, publisher_id)
    WHERE status = 'active';

CREATE TABLE subscription_authorization_keys (
    authorization_id UUID PRIMARY KEY
        REFERENCES subscription_authorizations (id) ON DELETE CASCADE,
    ciphertext BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE subscription_renewal_attempts (
    authorization_id UUID NOT NULL
        REFERENCES subscription_authorizations (id) ON DELETE CASCADE,
    period_start TIMESTAMPTZ NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TIMESTAMPTZ NOT NULL,
    last_error TEXT,
    PRIMARY KEY (authorization_id, period_start)
);

CREATE TABLE wallet_principals (
    wallet_address TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT wallet_principals_address_nonempty
        CHECK (wallet_address <> '')
);

CREATE TABLE publishers (
    id UUID PRIMARY KEY,
    handle TEXT NOT NULL,
    display_name TEXT NOT NULL,
    owner_address TEXT NOT NULL
        REFERENCES wallet_principals (wallet_address),
    description TEXT NOT NULL,
    status TEXT NOT NULL,
    default_article_price NUMERIC NOT NULL,
    default_subscription_price NUMERIC NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT publishers_handle_key UNIQUE (handle),
    CONSTRAINT publishers_handle_nonempty CHECK (handle <> ''),
    CONSTRAINT publishers_status_valid
        CHECK (status IN ('active', 'disabled')),
    CONSTRAINT publishers_article_price_positive
        CHECK (default_article_price > 0),
    CONSTRAINT publishers_subscription_price_positive
        CHECK (default_subscription_price > 0)
);

CREATE TABLE articles (
    id UUID PRIMARY KEY,
    publisher_id UUID NOT NULL REFERENCES publishers (id),
    slug TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    author TEXT,
    published_at TIMESTAMPTZ,
    price NUMERIC,
    license TEXT,
    summary TEXT,
    tags TEXT[],
    key_claims TEXT[],
    allowed_excerpts TEXT[],
    suggested_citation TEXT,
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT articles_publisher_slug_key UNIQUE (publisher_id, slug),
    CONSTRAINT articles_slug_nonempty CHECK (slug <> ''),
    CONSTRAINT articles_price_positive CHECK (price IS NULL OR price > 0),
    CONSTRAINT articles_status_valid CHECK (status IN ('draft', 'published')),
    CONSTRAINT articles_published_complete CHECK (
        status = 'draft' OR (
            slug <> ''
            AND title <> ''
            AND author IS NOT NULL AND author <> ''
            AND summary IS NOT NULL AND summary <> ''
            AND license IS NOT NULL AND license <> ''
            AND suggested_citation IS NOT NULL AND suggested_citation <> ''
            AND tags IS NOT NULL AND cardinality(tags) > 0
            AND key_claims IS NOT NULL AND cardinality(key_claims) > 0
            AND allowed_excerpts IS NOT NULL AND cardinality(allowed_excerpts) > 0
            AND price IS NOT NULL
            AND published_at IS NOT NULL
        )
    )
);

CREATE TABLE one_time_purchases (
    id UUID PRIMARY KEY,
    wallet_address TEXT NOT NULL
        REFERENCES wallet_principals (wallet_address),
    article_id UUID NOT NULL REFERENCES articles (id),
    payment_reference TEXT NOT NULL,
    amount NUMERIC NOT NULL,
    currency TEXT NOT NULL,
    network TEXT NOT NULL,
    receipt JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT one_time_purchases_payment_reference_key
        UNIQUE (payment_reference),
    CONSTRAINT one_time_purchases_wallet_article_key
        UNIQUE (wallet_address, article_id),
    CONSTRAINT one_time_purchases_reference_nonempty
        CHECK (payment_reference <> ''),
    CONSTRAINT one_time_purchases_amount_positive CHECK (amount > 0)
);

CREATE TABLE subscriptions (
    id UUID PRIMARY KEY,
    wallet_address TEXT NOT NULL
        REFERENCES wallet_principals (wallet_address),
    publisher_id UUID NOT NULL REFERENCES publishers (id),
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    payment_reference TEXT NOT NULL,
    amount NUMERIC NOT NULL,
    currency TEXT NOT NULL,
    network TEXT NOT NULL,
    receipt JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT subscriptions_payment_reference_key
        UNIQUE (payment_reference),
    CONSTRAINT subscriptions_wallet_publisher_period_key
        UNIQUE (wallet_address, publisher_id, period_start, period_end),
    CONSTRAINT subscriptions_period_valid CHECK (period_end > period_start),
    CONSTRAINT subscriptions_amount_positive CHECK (amount > 0)
);

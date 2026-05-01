# Thoth Backend Architecture Spec

## Summary

The backend target is a FastAPI production API that powers a multi-publisher
knowledge marketplace. It stores Markdown-native articles, enforces wallet
principal entitlements, integrates Tempo/MPP payments, supports PPV and
per-publisher subscriptions, records usage and feedback, and exposes
agent-native research/search APIs.

This spec describes the target state. It is not a compatibility plan for the
demo backend.

## Current State

The current backend is a compact demo:

- Article metadata and context are read from Postgres-backed article rows.
- `app/routes/articles.py` exposes public article metadata.
- `app/routes/context.py` exposes paid structured context through MPP.
- `app/db.py` stores articles, wallet principals, purchases, subscriptions,
  usage, and feedback in Postgres.
- `app/config.py` validates Tempo environment safety.

The production backend should keep the useful concepts but hard-cutover the
runtime model:

- Static Markdown directory becomes publisher-managed persisted articles.
- Postgres is required through `DATABASE_URL`.
- Context-only paid access becomes full article plus context entitlement.
- Single implicit publisher becomes explicit multi-publisher domain.
- Basic listing becomes search, ranking, and usefulness signals.

## Architecture Principles

- FastAPI remains the API boundary.
- Postgres is the source of truth for publishers, articles, entitlements,
  purchases, subscriptions, usage, and feedback.
- Markdown remains the canonical article content format.
- Backend is the only source of truth for access state.
- Tempo wallet principal is the primary identity for humans and agents.
- Each publisher has one receiving Tempo wallet in V1.
- V1 payments are direct to publishers with no Thoth platform fee.
- Article purchases are one-time entitlements.
- Publisher subscriptions use fixed 30-day periods.
- Payment and subscription receipt data must be durable and auditable.
- Invalid publisher input hard-fails at publishing boundaries.
- Public APIs never expose full paid Markdown or full paid context.
- Agent APIs are first-class, not scraped from human pages.

## Core Domain Model

### Publisher

Represents a publication that can receive payments and publish articles.

Required fields:

- `id`.
- `handle`.
- `name`.
- `description`.
- `recipient_wallet`.
- `status`.
- `created_at`.
- `updated_at`.

Constraints:

- `handle` is unique.
- `recipient_wallet` is required for paid publication.
- Archived or disabled publishers cannot publish new paid articles.

### Article

Represents one Markdown-native piece of knowledge.

Required fields:

- `id`.
- `publisher_id`.
- `slug`.
- `title`.
- `author`.
- `published_date`.
- `status`.
- `summary`.
- `tags`.
- `key_claims`.
- `allowed_excerpts`.
- `suggested_citation`.
- `license`.
- `markdown_body`.
- `ppv_price`.
- `subscriber_access`.
- `created_at`.
- `updated_at`.
- `published_at`.

Constraints:

- `(publisher_id, slug)` is unique.
- Published articles require valid Markdown and all required metadata.
- Public preview responses exclude `markdown_body`.
- Archived articles remain available to existing entitled wallets unless an
  explicit product/legal policy later says otherwise.

### Wallet Principal

Represents the account identity used for access decisions.

Required fields:

- `wallet_address`.
- `network`.
- `created_at`.
- `last_seen_at`.

The wallet principal can represent a human, an agent, or both. The backend does
not need separate user classes for V1 unless app-account login is added later.

### Purchase

Represents one PPV article purchase.

Required fields:

- `id`.
- `wallet_address`.
- `publisher_id`.
- `article_id`.
- `payment_reference`.
- `amount`.
- `currency`.
- `network`.
- `receipt`.
- `created_at`.

Constraints:

- `payment_reference` is unique.
- A purchase grants access only to its `article_id`.
- A duplicate payment reference for a different article or wallet is an error,
  not a silent reuse path.

### Subscription

Represents a wallet's subscription to one publisher.

Required fields:

- `id`.
- `wallet_address`.
- `publisher_id`.
- `status`.
- `current_period_start`.
- `current_period_end`.
- `payment_reference`.
- `amount`.
- `currency`.
- `network`.
- `receipt`.
- `created_at`.
- `updated_at`.

Constraints:

- Active subscription grants access only to eligible articles from the same
  publisher.
- Expired, cancelled, or invalid subscriptions do not grant access.
- Subscription status is derived from verified Tempo payment state and persisted
  backend state.

### Usage Event

Represents an access or usage signal.

Required fields:

- `id`.
- `wallet_address`.
- `article_id`.
- `publisher_id`.
- `event_type`.
- `source`.
- `created_at`.

Valid `event_type` examples:

- `preview_viewed`.
- `markdown_accessed`.
- `context_accessed`.
- `search_result_clicked`.
- `citation_exported`.

Valid `source` values:

- `human`.
- `agent`.

### Feedback

Represents explicit useful/not-useful feedback.

Required fields:

- `id`.
- `wallet_address`.
- `article_id`.
- `is_useful`.
- `created_at`.
- `updated_at`.

Constraints:

- Feedback requires article entitlement.
- One current feedback record per wallet/article.
- Updating feedback changes the record instead of creating vote spam.

## Entitlement Model

The backend computes access from wallet principal plus persisted payment state.

An article is accessible when at least one condition is true:

- Wallet has a valid PPV purchase for the article.
- Wallet has an active subscription to the article's publisher and the article
  allows subscriber access.
- Wallet is authorized as the article's publisher owner.

Access denial returns a payment challenge or locked-access response depending
on the endpoint:

- Human preview endpoints return public metadata plus access state.
- Paid Markdown/context endpoints return `402 Payment Required` when payment is
  required.
- Publisher editing endpoints return authorization errors for non-owners.

Client-provided access state must never be trusted.

## Payment Architecture

### PPV

PPV keeps the existing MPP challenge pattern:

1. Request paid Markdown or paid context.
2. Backend checks entitlement.
3. If missing, backend returns payment challenge.
4. Caller completes payment.
5. Backend verifies receipt.
6. Backend persists purchase.
7. Paid content is returned.

PPV memo/reference must bind payment to:

- Publisher.
- Article.
- Wallet principal.
- Amount.
- Currency.
- Network.

### Subscriptions

Subscriptions use Tempo scheduled or recurring payment capability as the target
payment primitive. Backend responsibilities:

- Start or describe subscription payment flow.
- Persist subscription records.
- Verify active subscription state.
- Enforce `current_period_start` and `current_period_end`.
- Deny access when subscription is expired or invalid.

The first production version should support per-publisher subscriptions only.
Global all-access subscriptions are out of scope.

## API Surface

### Public Preview APIs

`GET /api/publishers`

Returns publisher directory with public metadata and aggregate usefulness
signals.

`GET /api/publishers/{publisher_handle}`

Returns publisher profile, subscription availability, article previews, and
wallet-aware access state when a wallet principal is present.

`GET /api/publishers/{publisher_handle}/articles/{article_slug}`

Returns article preview, price, access policy, usefulness score, and access
state. It never returns full Markdown.

### Paid Content APIs

`GET /api/publishers/{publisher_handle}/articles/{article_slug}/markdown`

Returns full Markdown when entitled. Returns payment challenge when PPV or
subscription is required.

`GET /api/publishers/{publisher_handle}/articles/{article_slug}/context`

Returns structured context package when entitled. Returns payment challenge when
PPV or subscription is required.

Context package fields:

- `summary`.
- `key_claims`.
- `allowed_excerpts`.
- `suggested_citation`.
- `license`.
- `article`.
- `publisher`.
- `receipt`.

### Search APIs

`POST /api/search/research`

Request fields:

- `objective`.
- `wallet_address`.
- `filters`.

Response result fields:

- `publisher`.
- `article`.
- `summary`.
- `matching_snippet`.
- `matching_reason`.
- `tags`.
- `usefulness_score`.
- `signal_summary`.
- `access_state`.
- `ppv_price`.
- `subscription_available`.
- `markdown_url`.
- `context_url`.

The endpoint must not leak full paid Markdown in snippets.

### Payment And Entitlement APIs

`GET /api/account/access`

Returns wallet-level purchases, subscriptions, and accessible articles.

`POST /api/payments/ppv`

Starts or describes the PPV flow for an article if the endpoint design needs a
separate initiation step beyond direct `402` challenge.

`POST /api/subscriptions`

Starts publisher subscription payment flow.

`GET /api/subscriptions/{publisher_handle}`

Returns subscription status for the calling wallet principal.

### Feedback APIs

`POST /api/articles/{article_id}/feedback`

Records useful/not-useful feedback for an entitled wallet.

`GET /api/articles/{article_id}/signals`

Returns public aggregate usefulness and usage signals.

### Publisher APIs

`POST /api/publishers`

Creates publisher profile for an authorized wallet principal.

`PATCH /api/publishers/{publisher_handle}`

Updates publisher metadata.

`POST /api/publishers/{publisher_handle}/articles`

Creates article draft from Markdown.

`PATCH /api/publishers/{publisher_handle}/articles/{article_slug}`

Updates article Markdown, metadata, price, and access policy.

`POST /api/publishers/{publisher_handle}/articles/{article_slug}/publish`

Validates and publishes article. Invalid Markdown or frontmatter hard-fails.

## Markdown Publishing Contract

Published Markdown requires frontmatter fields:

- `title`.
- `author`.
- `published_date`.
- `summary`.
- `tags`.
- `key_claims`.
- `allowed_excerpts`.
- `suggested_citation`.
- `license`.
- `ppv_price`.
- `subscriber_access`.

Validation rules:

- Required fields must be present.
- List fields must be non-empty where required.
- `ppv_price` must be finite and non-negative.
- `published_date` must parse as a date.
- Slug is derived from publisher plus article slug and must be unique within
  publisher.
- Markdown body must be non-empty.

The backend stores canonical Markdown and parsed metadata. Public preview uses
metadata and allowed excerpts. Paid Markdown endpoint returns the full canonical
Markdown.

## Search And Ranking Architecture

V1 search should support agent research objectives as the primary contract.

Indexable public fields:

- Title.
- Summary.
- Tags.
- Key claims.
- Allowed excerpts.
- Publisher metadata.

Indexable paid fields:

- Full Markdown can be used internally for retrieval and ranking only if result
  snippets are constrained to public preview fields or approved excerpts.

Ranking inputs:

- Text or semantic relevance to objective.
- Publisher trust/usefulness.
- Article usefulness.
- Recency.
- Access state for wallet.
- Price or subscription availability.

Usefulness score inputs:

- PPV purchases.
- Markdown accesses.
- Context accesses.
- Repeat access.
- Agent citations or exports.
- Subscription retention.
- Explicit useful/not-useful feedback.

The response should expose enough signal summary to be trusted, but not enough
raw event detail to leak private behavior.

## Operational Requirements

- Postgres migrations are required for schema changes.
- Configuration must hard-fail when required payment, database, or network
  settings are missing.
- Production CORS must be restricted to configured frontend origins.
- Structured logs must avoid secrets and raw authorization headers.
- Health endpoint must distinguish process liveness from dependency readiness.
- Payment references and receipts must be auditable.
- Mainnet operation must keep explicit safety checks.

## Deployment Requirements

The backend production target is a Render web service backed by Render
Postgres. The service must run as a normal long-lived ASGI app and bind to
`0.0.0.0` on the platform-provided port.

Required environments:

- Local: developer `.env`, local or disposable database, Tempo testnet.
- Staging: Render backend, staging Postgres, Tempo testnet, staging frontend
  origin only.
- Production: Render backend, production Postgres, Tempo mainnet only after
  safety confirmation.

Required backend environment variables:

- `ENVIRONMENT`.
- `TEMPO_NETWORK`.
- `MAINNET_CONFIRMATION`.
- `MPP_REALM`.
- `MPP_SECRET_KEY`.
- `PUBLISHER_RECIPIENT`.
- `PATHUSD_ADDRESS`.
- `DATABASE_URL`.
- `CORS_ORIGINS`.
- `FRONTEND_BASE_URL`.

The backend requires `DATABASE_URL` with the `postgresql+psycopg` SQLAlchemy
scheme.

Required deploy behavior:

- Run migrations before starting the production web service.
- Expose `/health/live` for process liveness and `/health/ready` for database
  and payment configuration readiness.
- Restrict CORS to the configured frontend domains.
- Log request IDs, payment references, and article/publisher IDs without
  logging authorization headers, private keys, receipts that contain secrets,
  or raw wallet credentials.
- Keep staging and production databases, MPP realms, and Tempo networks
  separate.

## Backend Milestone Candidates

### Backend M1: Production Persistence

Deliver:

- Postgres setup and migrations.
- Production tables for publishers, articles, purchases, subscriptions, usage
  events, and feedback.
- Removal of SQLite as production runtime persistence.

Acceptance criteria:

- Production API uses Postgres.
- Schema constraints enforce publisher/article/payment uniqueness.
- Article rows can represent the fields needed by existing public route shapes.

### Backend M2: Publisher Markdown Publishing

Deliver:

- Publisher CRUD.
- Markdown draft creation/update.
- Frontmatter validation.
- Publish endpoint.

Acceptance criteria:

- Valid Markdown publishes.
- Invalid Markdown hard-fails.
- Preview responses exclude full Markdown.
- Publisher ownership is enforced.

### Backend M3: PPV Entitlements

Deliver:

- Article PPV payment flow.
- Receipt persistence.
- Entitlement checks for paid Markdown and paid context.

Acceptance criteria:

- Missing purchase returns payment challenge.
- Valid purchase unlocks only the purchased article.
- Duplicate or mismatched payment references hard-fail.

### Backend M4: Publisher Subscriptions

Deliver:

- Per-publisher subscription model.
- Subscription payment flow.
- Active/expired subscription checks.

Acceptance criteria:

- Active subscription unlocks eligible articles for that publisher.
- Subscription does not unlock other publishers.
- Expired subscription returns locked/payment-required state.

### Backend M5: Agent Search And Usefulness

Deliver:

- Research-objective search endpoint.
- Usage event capture.
- Feedback endpoint.
- Usefulness scoring.

Acceptance criteria:

- Search returns ranked article candidates with price and access state.
- Paid body text is not leaked in public snippets.
- Usage and explicit feedback affect usefulness signals.

### Backend M6: Production Hardening

Deliver:

- Deployment-ready config.
- Restricted CORS.
- Structured logging.
- Readiness checks.
- Real Tempo testnet validation scripts or documentation.

Acceptance criteria:

- `ruff`, `ruff format --check`, `pyright`, and `pytest` pass.
- Testnet PPV path is proven.
- Subscription validation path is proven or explicitly blocked by Tempo
  dependency with a documented replacement verification.

## Test Plan

Required backend tests:

- Markdown validation accepts valid content and rejects invalid frontmatter.
- Public preview excludes full Markdown.
- PPV purchase grants one article only.
- Publisher subscription grants only eligible articles from one publisher.
- Missing or expired entitlement denies paid Markdown and paid context.
- Duplicate payment reference for different article/wallet hard-fails.
- Research endpoint returns access state, price, usefulness score, and paid URLs.
- Feedback requires entitlement and updates one current vote.
- Usage events are recorded for paid Markdown and context access.
- CORS and production safety checks enforce configured production constraints.

Required commands:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
```

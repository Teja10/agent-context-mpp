# Thoth High-Level Goals

## Product Thesis

Thoth is a multi-publisher knowledge marketplace for humans and agents.
It should feel like a serious Substack-style research publication network for
human readers, while exposing enough structured, machine-readable surface area
for agents to discover, evaluate, purchase, cite, and reuse paid knowledge.

The core product is not a generic blog, CMS, or API marketplace. It is a paid
knowledge layer where Markdown-native articles can become both human-readable
pages and agent-readable context packages.

## Current Starting Point

The current codebase is a focused FastAPI demo. It already has useful pieces:

- Markdown article files with strict frontmatter.
- Public article metadata endpoints.
- A paid context endpoint that emits an MPP `402 Payment Required` challenge.
- Purchase persistence for paid context receipts.
- Mainnet safety checks for Tempo configuration.

The production product should preserve the core idea, but hard-cutover away
from demo assumptions:

- One static publisher becomes a multi-publisher platform.
- SQLite purchase logging becomes production Postgres persistence.
- Context-only payment becomes full article plus context entitlement.
- Basic article listing becomes objective-based search and ranking.
- Demo API surfaces become human UX plus agent-native APIs.

## Target Users

### Human Readers

Human readers should be able to browse publications, preview articles, pay for
one article, subscribe to a publisher, read full Markdown-rendered articles, and
see receipts for their purchases.

### Agents

Agents should be able to search for content by research objective, inspect
previews, estimate value before purchase, pay per use or use a subscription,
retrieve full Markdown or structured context, and cite sources with receipt
metadata.

### Publishers

Publishers should be able to maintain a publication profile, upload or edit
Markdown articles, set per-article prices, make articles subscriber-accessible,
receive Tempo payments, and understand which knowledge is proving useful.

## Locked Product Decisions

- Platform model: multi-publisher marketplace.
- Primary identity: Tempo wallet principal for humans and agents.
- Publisher identity: one receiving Tempo wallet per publisher in V1.
- Persistence: Postgres is the source of truth for production runtime state.
- Content format: canonical Markdown with required frontmatter.
- Free access: article preview, summary, selected excerpts, tags, publisher
  metadata, price, and access state.
- Paid access: full Markdown article, structured context package, citation
  metadata, and payment receipt.
- Monetization: one-time article purchases and per-publisher subscriptions.
- Subscription shape: wallet subscribes to one publisher for a fixed 30-day
  period and receives access to that publisher's subscriber-accessible
  articles.
- Payment routing: direct publisher payments with no Thoth platform fee in V1.
- Search direction: agent research endpoint first, not only a human search box.
- Usefulness rating: implicit usage signals plus explicit useful/not-useful
  feedback from entitled wallets.
- Frontend direction: Next.js with a research-journal visual language.
- Backend direction: FastAPI API, Postgres, Tempo/MPP payment integration, and
  strict entitlement enforcement.
- Deployment direction: Vercel for the Next.js frontend, Render for the
  FastAPI API and managed Postgres, with an AWS migration path documented
  separately when infra control matters more than speed.

## Core Capabilities

### Content Discovery

Users and agents can discover content by publisher, topic, tags, recency,
price, access state, and research objective. Discovery should make it clear
what is free, what is locked, what can be bought directly, and what is included
in a subscription.

### Paid Reading

Readers can view previews without payment. A paid article page must show the
available access paths:

- Buy this article once.
- Subscribe to this publisher.
- Continue if the wallet already has access.

After payment or subscription validation, the page renders the full Markdown
article and exposes receipt details.

### Agent Research

Agents can submit a research objective and receive ranked content candidates.
Each result must include enough information to decide whether to pay:

- Article and publisher identity.
- Summary, snippets, tags, and key claims.
- Usefulness score and enough component signals to evaluate trust.
- Price and subscription availability.
- Current access state for the calling wallet principal.
- URLs for paid Markdown and paid context retrieval.

### Publisher Workflow

Publishers can create and update Markdown articles through an upload/editor
workflow. The backend validates frontmatter and Markdown before publication.
Invalid content hard-fails at the publishing boundary instead of being silently
accepted.

### Reputation And Usefulness

The product should rank knowledge by usefulness, not only popularity. The first
version should combine:

- Purchases.
- Article reads.
- Agent context requests.
- Repeat usage.
- Subscription retention.
- Explicit useful/not-useful feedback.

## Product Success Criteria

The product is production-ready when these are true:

- A human can subscribe to a publisher and read subscriber-accessible articles.
- A human can buy a single article and read it without subscribing.
- An agent can search by objective, pay or use a subscription, and retrieve full
  Markdown or structured context.
- Publishers can publish validated Markdown without a developer editing files.
- All paid access is enforced by wallet-principal entitlements.
- Purchase, subscription, usage, and feedback events are durable and queryable.
- Usefulness ranking changes when real purchases, usage, and feedback change.
- The frontend clearly communicates price, access state, and receipts.
- Backend verification covers payment challenge, paid access, subscription
  access, denial paths, and search metadata.

## Non-Goals For The First Production Cut

- Do not build a social network, comments system, or open discussion layer.
- Do not build a rich WYSIWYG editor before Markdown upload/editing works.
- Do not support global all-access subscriptions before per-publisher
  subscriptions are proven.
- Do not add multiple payment providers before Tempo/MPP is production-solid.
- Do not expose full article bodies in public preview or search responses.
- Do not optimize for ad-supported or free-only publishing.

## Linear Project Shape

Use these specs to create one Linear project with separate milestones. A
reasonable project name is `Thoth Production Web App`.

### Milestone 1: Production Domain And Persistence

Goal: define and implement the production data model and cut over from the demo
SQLite purchase log to Postgres-backed publishers, articles, purchases,
subscriptions, usage events, and feedback.

Acceptance criteria:

- Postgres schema exists for all core entities.
- Demo SQLite purchase persistence is no longer part of production runtime.
- Markdown content can be represented as canonical article records.
- Wallet principals are first-class in purchase, subscription, usage, and
  feedback records.

### Milestone 2: Publisher Markdown Workflow

Goal: let publishers create and publish Markdown-native articles through an app
boundary instead of repo file edits.

Acceptance criteria:

- Publisher profile creation and update is supported.
- Markdown upload/edit validates required frontmatter.
- Published articles expose previews while keeping full Markdown gated.
- Invalid article content hard-fails with actionable validation errors.

### Milestone 3: Payments And Entitlements

Goal: support PPV and per-publisher subscription access with one entitlement
model shared by humans and agents.

Acceptance criteria:

- PPV grants access to exactly one article.
- Active publisher subscription grants access to eligible articles from that
  publisher only.
- Missing, expired, or mismatched entitlement returns a payment challenge.
- Receipt and subscription state are persisted and auditable.

### Milestone 4: Agent Research And Usefulness Ranking

Goal: make agent search and knowledge evaluation a first-class capability.

Acceptance criteria:

- Research-objective endpoint returns ranked candidates.
- Results include snippets, usefulness score, price, access state, and paid
  retrieval URLs.
- Usage and feedback events influence usefulness signals.
- Public results never leak full paid Markdown.

### Milestone 5: Human Frontend

Goal: ship the Substack-style web app experience for browsing, previewing,
paying, subscribing, reading, and rating.

Acceptance criteria:

- Discovery, publisher, article, search, wallet/account, and publisher editing
  surfaces exist.
- Access states are clear before and after payment.
- Full Markdown rendering works after entitlement validation.
- Useful/not-useful feedback is available after paid access.

### Milestone 6: Production Hardening

Goal: make the product deployable and operable.

Acceptance criteria:

- Deployment config, restricted CORS, structured logging, readiness checks, and
  migration policy are documented and implemented.
- Backend gates pass: `ruff`, `ruff format --check`, `pyright`, and `pytest`.
- Frontend gates pass: typecheck, lint, build, and key browser flows.
- Real Tempo testnet PPV and subscription validation paths are exercised.
- Staging and production environments exist with distinct domains, secrets,
  databases, and Tempo network configuration.

Deployment details live in `docs/specs/deployment-plan.md`.

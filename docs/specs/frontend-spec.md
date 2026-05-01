# Thoth Frontend Spec

## Summary

The frontend is a Next.js web app for a multi-publisher knowledge marketplace.
It should give humans a premium research-publication experience while making
agent-readable paid knowledge visible, understandable, and trustworthy.

The interface should not look like a generic SaaS dashboard. It should feel like
a serious research journal with a payment rail and machine access built into the
reading experience.

## Product Goals

- Let human readers browse publishers and articles without needing to understand
  MPP or agent workflows.
- Let agents and technical buyers identify which paid knowledge is worth buying.
- Make payment choices clear: buy one article once or subscribe to the
  publisher for a fixed 30-day period.
- Make access state obvious before and after payment.
- Show usefulness and trust signals without turning the product into a social
  feed.
- Keep Markdown as the visible editorial substrate, not an implementation
  detail hidden from readers.
- Present direct publisher payments with no Thoth platform fee in V1.

## Visual Direction

### Visual Thesis

Thoth should feel like an institutional research desk crossed with an
independent paid publication: editorial, precise, citation-forward, and calm,
with subtle ledger/payment details embedded into the interface.

### Design Language

- Editorial density over marketing spaciousness.
- Strong typography, restrained color, high information quality.
- Article pages should prioritize reading, citation, and access state.
- Search should feel like a research console, not a consumer search engine.
- Publisher pages should feel like publications, not creator profile cards.
- Payment and receipt UI should feel trustworthy and inspectable.

### Avoid

- Generic SaaS card mosaics.
- Purple-gradient AI product aesthetics.
- Oversized marketing hero sections once the user is inside the app.
- Decorative charts that do not affect a purchase or research decision.
- Social-media affordances such as comments, follower counts, and noisy badges.

### Suggested Art Direction

- Typography: one distinctive serif for editorial headings and article titles,
  one highly legible sans or mono for metadata, receipts, and search controls.
- Palette: paper-like reading surfaces, ink-heavy text, muted steel or olive
  accents, and a single sharp accent for payment/access state.
- Texture: subtle scanline, paper grain, or archive-index treatment can support
  the research-journal feel if it stays quiet.
- Motion: deliberate transitions for search results, paywall unlock, and
  article table-of-contents movement.

## Information Architecture

### Top-Level Routes

- `/`: discovery and research-objective search entry.
- `/publishers`: publisher directory.
- `/p/{publisher_handle}`: publisher page.
- `/p/{publisher_handle}/{article_slug}`: article preview or full article.
- `/search`: full research search workspace.
- `/account`: wallet, subscriptions, purchases, receipts, and agent access.
- `/publish`: publisher workspace for Markdown upload/editing.
- `/publish/articles/{article_id}`: article editor and validation state.

Route names can be adjusted during implementation, but these surfaces must
exist as distinct product concepts.

## Core Pages

### Discovery Home

Purpose: orient users and start research.

Required content:

- Thoth brand and one-sentence product promise.
- Research-objective search input as the primary action.
- Ranked feed of useful/recent paid knowledge.
- Publisher highlights with topic focus and subscription availability.
- Explanation-light payment affordance: PPV and per-publisher subscriptions.

UX requirements:

- The first viewport must make the product name and research search obvious.
- Search is not a tiny nav field; it is the main discovery action.
- Human readers should be able to browse without connecting a wallet.

### Publisher Page

Purpose: let users evaluate and subscribe to a publisher.

Required content:

- Publisher name, handle, description, recipient/payment identity, and status.
- One receiving Tempo wallet for the publisher.
- Subscribe CTA with price/period once subscription pricing exists.
- Article archive with previews, prices, access state, and usefulness signals.
- Publisher-level usefulness and activity summary.
- Clear distinction between public, PPV, and subscriber-accessible articles.

Access states:

- Not connected: show preview and connect/pay actions.
- Connected without access: show PPV/subscription choices.
- Connected with active subscription: mark included articles as accessible.
- Publisher owner: show edit/publish actions.

### Article Page

Purpose: convert preview readers into paid readers and serve full Markdown after
entitlement.

Public preview must include:

- Title.
- Publisher and author byline.
- Publication date.
- Summary.
- Tags/topics.
- Key claims preview.
- Selected excerpts.
- Price and subscription availability.
- Usefulness score and signal summary.

Locked state must include:

- Buy article CTA.
- Subscribe to publisher CTA.
- Explanation that paid access includes full Markdown and agent context.
- Visible access state for the current wallet.

Unlocked state must include:

- Full Markdown-rendered article.
- Structured context link or panel.
- Citation metadata.
- Payment receipt summary.
- Useful/not-useful feedback action.

Markdown rendering requirements:

- Headings, paragraphs, links, lists, block quotes, code blocks, tables, and
  footnotes must render cleanly.
- Long articles need a readable table of contents on desktop.
- Mobile reading must keep line length and metadata usable.

### Research Search Workspace

Purpose: help humans and agents find paid knowledge for an objective.

Required inputs:

- Research objective text.
- Optional filters: publisher, topic/tag, price range, access state, recency,
  content type.
- Wallet-aware toggle for accessible-only results.

Required result fields:

- Article title.
- Publisher.
- Summary or generated matching rationale.
- Snippet or approved excerpt.
- Tags/topics.
- Usefulness score.
- Access state.
- PPV price.
- Subscription availability.
- Paid Markdown endpoint.
- Paid context endpoint.

UX requirements:

- Results must make the purchase decision easy without leaking full paid text.
- Results should group or annotate already-accessible content.
- Agent API availability should be visible for technical users.

### Account And Wallet Page

Purpose: show wallet-principal state.

Required content:

- Connected wallet/account principal.
- Active publisher subscriptions.
- PPV article purchases.
- Receipts.
- Feedback history.
- Agent access instructions.
- Links to paid Markdown/context endpoints for purchased content.

### Publisher Workspace

Purpose: let publishers manage Markdown-native content.

Required content:

- Publisher profile editor.
- Markdown upload or editor.
- Frontmatter validation results.
- Preview rendering.
- Article status: draft, published, archived.
- Pricing and access policy controls.
- Publication action that fails on invalid required fields.

V1 can be sparse and utility-focused. It should not attempt to be a full rich
text editor.

## Access State Model

The frontend must represent these states consistently:

- `public_preview`: no wallet or entitlement required.
- `locked`: wallet has no article purchase or active publisher subscription.
- `ppv_available`: article can be bought once.
- `subscription_available`: publisher subscription grants access.
- `purchased`: wallet bought the article.
- `subscribed`: wallet has active publisher subscription.
- `publisher_owner`: wallet can edit publisher/article data.
- `payment_pending`: payment flow has started but entitlement is not confirmed.
- `payment_failed`: payment failed or was rejected.

Do not infer access from client state alone. The backend is the entitlement
source of truth.

## Payment UX

### PPV Flow

1. User opens locked article.
2. User chooses buy article.
3. Frontend requests paid access and receives payment challenge or payment
   session details from backend.
4. User completes Tempo/MPP payment.
5. Frontend refreshes entitlement state.
6. Full Markdown, context, receipt, and feedback UI appear.

### Subscription Flow

1. User opens publisher or locked article.
2. User chooses subscribe to publisher.
3. Frontend starts Tempo subscription payment flow.
4. Backend confirms active publisher subscription.
5. Frontend refreshes publisher and article access state.
6. Subscriber-accessible articles become unlocked for that publisher.

### Receipt UX

Receipts should be visible but compact:

- Payment reference.
- Amount.
- Currency.
- Publisher.
- Article or subscription.
- Timestamp.
- Network.

Never display secrets, private auth headers, or raw credentials.

## Rating And Usefulness UX

### Explicit Feedback

After a user has access to an article, show a simple prompt:

- Useful.
- Not useful.

The UI should avoid star ratings in V1 because they imply precision that the
product does not yet have.

### Aggregate Display

Show usefulness as a trust signal, for example:

- Useful to 84 percent of paid readers.
- Frequently cited by agents.
- High repeat usage.

Exact label design can change, but the interface must separate:

- Popularity signals.
- Usefulness signals.
- Access/price signals.

## API Dependencies

The frontend expects backend APIs for:

- Publisher directory and publisher detail.
- Article previews and full paid Markdown.
- Paid context package retrieval.
- Research-objective search.
- Wallet access state.
- PPV payment challenge/confirmation.
- Subscription creation and status.
- Receipt listing.
- Feedback submission.
- Publisher profile and article publishing.

## Deployment Requirements

The frontend production target is Vercel. It should be deployed as a separate
Next.js app that talks to the FastAPI backend through configured API origins.

Required environments:

- Preview: every pull request gets a Vercel preview deployment.
- Staging: points at the staging backend and Tempo testnet configuration.
- Production: points at the production backend and Tempo mainnet configuration
  only after mainnet safety gates pass.

Required environment variables:

- `NEXT_PUBLIC_API_BASE_URL`.
- `NEXT_PUBLIC_THOTH_ENVIRONMENT`.
- `NEXT_PUBLIC_TEMPO_NETWORK`.

Frontend secrets must not use `NEXT_PUBLIC_`. Payment secrets, MPP secrets,
database URLs, and publisher recipient secrets belong only in backend runtime
configuration.

Required deployment behavior:

- Production frontend domain is separate from the backend API domain.
- API calls use the configured backend origin, not same-origin assumptions.
- Preview deployments can call staging backend only when staging test data is
  acceptable.
- The app must render locked states cleanly when the backend returns payment
  required or no entitlement.
- Build output must not bake production API URLs into preview deployments.

## Frontend Milestone Candidates

### Frontend M1: App Shell And Discovery

Deliver:

- Next.js app shell.
- Research-journal visual system.
- Home/discovery route.
- Publisher directory and publisher page read-only views.
- Article preview route.

Acceptance criteria:

- Public browsing works without a wallet.
- Article preview never renders full paid Markdown.
- Mobile and desktop layouts are readable and non-overlapping.

### Frontend M2: Article Paywall And Reading

Deliver:

- Article locked/unlocked states.
- PPV and subscription CTAs.
- Full Markdown renderer.
- Receipt summary.

Acceptance criteria:

- Backend access state controls locked vs unlocked rendering.
- Full Markdown only appears after entitlement.
- Payment-pending and payment-failed states are represented.

### Frontend M3: Research Search Workspace

Deliver:

- Objective-based search page.
- Filters and access-state result annotations.
- Result actions for preview, PPV, subscription, Markdown, and context.

Acceptance criteria:

- Search results provide enough information to evaluate purchase.
- Already-accessible content is visually distinct.
- Paid snippets do not leak full article bodies.

### Frontend M4: Account And Publisher Workspace

Deliver:

- Wallet/account page.
- Purchase and subscription listing.
- Publisher profile editor.
- Markdown upload/editor with validation feedback.

Acceptance criteria:

- A wallet can see its purchases and subscriptions.
- A publisher can validate Markdown before publishing.
- Invalid Markdown cannot be published from the UI.

## Verification

- Typecheck passes.
- Lint passes.
- Production build passes.
- Browser validation covers desktop and mobile for discovery, article preview,
  locked article, unlocked article, search, account, and publisher workspace.
- Frontend tests cover access-state rendering and Markdown rendering.

## Open Dependencies

- Exact Tempo browser payment integration details.
- Final backend endpoint paths and response models.
- Final subscription confirmation flow.

These are backend/product dependencies, not frontend design blockers.

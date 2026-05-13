# Thoth Frontend Design Spec

## Context

Thoth is a machine-payable content marketplace on the Tempo blockchain. Publishers create articles, consumers pay to read them in PATHUSD, and AI agents purchase structured context packages via the MPP API. The backend (FastAPI + Postgres) is complete — it handles wallet auth (EIP-191), article CRUD with markdown/YAML frontmatter, MPP payment gating, and one-time purchases. No frontend exists yet. This spec defines the initial web frontend.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Framework | Next.js (App Router) | SSR for article SEO, first-class Privy/wagmi support, RSC for fast article pages |
| Wallet auth | Privy (all-in-one) | Handles MetaMask/Coinbase/WalletConnect AND email/Google with embedded wallets |
| Editor library | Tiptap | Best markdown round-tripping for YAML frontmatter API, fully headless for custom styling |
| Aesthetic | Neo-Academic | Warm ivory (#fafaf8), espresso (#2c2416), brass (#c9a962), italic serif headings (Georgia), clean sans body |
| Gas strategy | User pays in PATHUSD | Tempo supports stablecoin fees — no separate gas token needed |
| Paywall model | Substack-style | Free: title, author, summary, tags. Paid: full article body |
| Page set | Minimal | Home/feed, article page, publisher dashboard, editor, login |

## Repo Structure

The backend moves into `backend/` and the frontend lives in `web/`:

```
agent-context-mpp/
├── backend/
│   ├── app/
│   ├── migrations/
│   ├── articles/
│   ├── tests/
│   ├── pyproject.toml
│   └── alembic.ini
├── web/
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx              # Root layout (providers)
│   │   │   ├── page.tsx                # Home/feed
│   │   │   ├── login/page.tsx          # Login
│   │   │   ├── articles/
│   │   │   │   └── [slug]/page.tsx     # Article reading + paywall
│   │   │   └── dashboard/
│   │   │       ├── page.tsx            # Publisher article list
│   │   │       └── editor/
│   │   │           ├── new/page.tsx
│   │   │           └── [slug]/page.tsx
│   │   ├── components/
│   │   │   ├── editor/
│   │   │   │   ├── article-editor.tsx      # Main editor container with tabs
│   │   │   │   ├── tiptap-editor.tsx       # Tiptap instance + toolbar
│   │   │   │   ├── metadata-form.tsx       # Settings tab fields
│   │   │   │   └── context-panel.tsx       # Agent context tab + preview toggle
│   │   │   ├── article/
│   │   │   │   ├── article-card.tsx        # Feed card
│   │   │   │   ├── article-view.tsx        # Full article renderer
│   │   │   │   └── paywall.tsx             # Purchase gate
│   │   │   └── layout/
│   │   │       ├── nav.tsx
│   │   │       └── wallet-button.tsx
│   │   ├── lib/
│   │   │   ├── api.ts                  # Fetch wrapper for FastAPI
│   │   │   ├── auth.ts                 # Challenge/sign flow
│   │   │   └── markdown.ts             # Tiptap <-> markdown <-> YAML frontmatter
│   │   └── providers/
│   │       └── index.tsx               # Privy + wagmi + TanStack Query
│   ├── public/
│   ├── package.json
│   ├── next.config.ts
│   ├── tailwind.config.ts
│   └── tsconfig.json
├── CLAUDE.md
└── .gitignore
```

## Design System

### Colors (CSS variables)

| Token | Value | Usage |
|-------|-------|-------|
| `--ivory` | `#fafaf8` | Page background |
| `--parchment` | `#fdfcf9` | Card/input backgrounds |
| `--sand` | `#f5f0e8` | Subtle backgrounds |
| `--tan` | `#f0e8d8` | Tag pills, hover states |
| `--khaki` | `#e8dcc8` | Borders |
| `--camel` | `#d4c5a9` | Input borders, muted elements |
| `--brass` | `#c9a962` | Accent (dividers, blockquote borders, active tab) |
| `--stone` | `#a89880` | Muted text, placeholders |
| `--umber` | `#8b7355` | Secondary text, labels |
| `--walnut` | `#6b5d4f` | Body text (secondary) |
| `--espresso` | `#2c2416` | Primary text, dark backgrounds |

### Typography

| Element | Font | Style |
|---------|------|-------|
| Page titles | Georgia, serif | 28px, italic |
| Article headings | Georgia, serif | 18-22px, italic, normal weight |
| Nav/brand | Georgia, serif | 16-18px, normal, letter-spacing: 1px |
| Labels | system-ui, sans-serif | 9-10px, uppercase, letter-spacing: 1-2px |
| Body text | system-ui, sans-serif | 14px, line-height: 1.8 |
| Metadata | system-ui, sans-serif | 12-13px |

### Components

- **Buttons**: `--espresso` background, `--ivory` text, 3px border-radius, 12px font
- **Tags**: `--tan` background, `--umber` text, 10px border-radius pill
- **Cards**: `--parchment` background, 1px `--khaki` border, 6px border-radius
- **Blockquotes**: 3px left border in `--brass`, italic, `--walnut` text
- **Status badges**: Green (#e8f5e8/#3a7a3a) for published, `--tan`/`--umber` for draft
- **Inputs**: White background, 1px `--camel` border, 4px border-radius
- **Dividers**: 2px `--brass`, 40px wide

## Pages

### 1. Home / Article Feed (`/`)

**Route**: `app/page.tsx` (Server Component)
**Data**: `GET /articles` — returns published article metadata
**Auth**: None required

Layout:
- Nav: "THOTH" brand left, "Connect Wallet" button right
- Hero: centered tagline "Knowledge, valued." with subtitle
- Article feed: vertical list, each card shows title (italic serif), author, date, summary, tags, price in PATHUSD
- Cards are full-width within a centered 720px container

### 2. Article Page (`/articles/[slug]`)

**Route**: `app/articles/[slug]/page.tsx` (Server Component for metadata, Client Component for paywall interaction)
**Data**: `GET /articles/{slug}` for metadata, `GET /articles/{slug}/context` for paid content
**Auth**: Required for purchase

Two states:

**Unpaid**: Title, author, date, summary (in gold-accented callout box), tags. Below: paywall card with "Continue reading" heading and "Purchase for X PATHUSD" button. Footer note: "Paid via Tempo · Fee in PATHUSD".

**Paid**: Same header + green "Purchased" badge. Full markdown body rendered below with article typography (serif headings, blockquotes with brass border).

**Payment flow**:
1. User clicks "Purchase"
2. Frontend calls `GET /articles/{slug}/context` without auth
3. Backend returns 402 with `WWW-Authenticate` header containing MPP payment challenge
4. Frontend parses challenge, uses Privy wallet to sign it
5. Frontend retries with `Authorization: WalletProof nonce.signature`
6. Backend charges via Tempo MPP, records purchase in `one_time_purchases`
7. Frontend calls `GET /articles/{slug}/body` with WalletProof header (new endpoint, see Backend Changes Required)
8. Backend verifies purchase exists for this wallet + article, returns full markdown body
9. Frontend renders article body with Neo-Academic typography

### 3. Login (`/login`)

**Route**: `app/login/page.tsx` (Client Component)
**Auth**: This IS the auth page

Card positioned in the upper-third of the page (not vertically centered — sits higher) on a warm gradient background with raised shadow effect (stacked box-shadows, no gold top border). Card contains:
- "Welcome to Thoth" header with brass divider
- Wallet options: MetaMask, Coinbase Wallet, WalletConnect
- "or" divider
- Email input + continue button
- Google login button
- "Powered by Privy" footer

**Auth flow**:
1. User connects via Privy → gets wallet address
2. Frontend calls `POST /auth/challenge` → gets nonce
3. Privy wallet signs nonce (EIP-191)
4. Frontend stores `WalletProof nonce.signature` for authenticated requests
5. Redirect to dashboard or previous page

### 4. Publisher Dashboard (`/dashboard`)

**Route**: `app/dashboard/page.tsx` (Client Component)
**Data**: `GET /me/publishers` then `GET /publishers/{handle}/articles`
**Auth**: Required (wallet principal)

Layout:
- Nav: "THOTH" brand + "Dashboard" label left, display name + truncated wallet right
- Header: "My Articles" with article count, "+ New Article" button
- Article list: bordered table-like list with title (italic serif), status badge (Published/Draft), date, price, Edit/View actions
- Drafts only show Edit, published articles show Edit + View

### 5. Article Editor (`/dashboard/editor/new` and `/dashboard/editor/[slug]`)

**Route**: `app/dashboard/editor/new/page.tsx` and `app/dashboard/editor/[slug]/page.tsx` (Client Components)
**Data**: `POST /publishers/{handle}/articles` (create), `PATCH /publishers/{handle}/articles/{slug}` (update), `POST .../publish` (publish)
**Auth**: Required (must be publisher owner)

Layout:
- Dark nav bar: "THOTH / Editor", auto-save indicator, "Save Draft" button (outline), "Publish" button (gold)
- Centered content area (640px max-width):
  - Inline title: large italic serif, auto-generates slug below
  - Three-tab bar: **Write** / **Agent Context** / **Settings**

**Write tab**:
- Tiptap toolbar (B, I, H1-H3, Quote, Code, List, Link)
- WYSIWYG editor area with Neo-Academic typography
- Optional toggle button to slide in a slim agent context preview panel on the right

**Agent Context tab**:
- Full-width context package editor
- Summary field (editable textarea)
- Key claims: numbered list with add/remove, each in its own card
- Allowed excerpts: quoted text with brass left border, add/remove
- Suggested citation: monospace field
- License selector
- Publish readiness: pill badges showing completion status of all required fields

**Settings tab**:
- Simple vertical form: author, price (PATHUSD), tags (pill input)

**Save/Publish flow**:
- Save Draft: assembles markdown with YAML frontmatter from form fields + Tiptap body → `PATCH /publishers/{handle}/articles/{slug}` with `{markdown: "---\n..."}` body
- Publish: calls `POST /publishers/{handle}/articles/{slug}/publish`. Backend validates all required fields are set. Returns 422 if missing fields.

## Auth Integration

### Privy Setup

Privy configured with:
- Login methods: wallet (MetaMask, Coinbase, WalletConnect), email, Google
- Embedded wallets: auto-create for email/social users
- Chain: Tempo (chain ID 4217 mainnet, 42431 moderato testnet)

### Backend Auth Bridge

Privy handles wallet connection. The backend uses its own EIP-191 challenge/response. The bridge:

1. Privy gives us a wallet (either external or embedded)
2. We call `POST /auth/challenge` to get a nonce
3. We use the Privy wallet's signing capability to sign the nonce
4. We send `Authorization: WalletProof <nonce>.<signature>` on all authenticated requests

This means the backend doesn't need to know about Privy — it only sees wallet signatures.

## Tech Stack

| Layer | Choice |
|-------|--------|
| Framework | Next.js 15 (App Router) |
| Styling | Tailwind CSS + CSS variables for theme |
| Wallet | Privy SDK (`@privy-io/react-auth`) |
| Web3 | wagmi v2 + viem |
| Editor | Tiptap (`@tiptap/react`) with markdown extensions |
| Data fetching | TanStack Query |
| Markdown | `@tiptap/extension-*` for editor, `react-markdown` + `remark-gfm` for article rendering |
| YAML | `yaml` package for frontmatter parsing/serialization |

## Data Flow

### Article Creation
```
User fills form → Tiptap body → serialize to markdown → prepend YAML frontmatter →
POST /publishers/{handle}/articles { markdown: "---\ntitle: ...\n---\n# Body" } →
Backend parses frontmatter + body → stores in Postgres → returns { id, slug, status: "draft" }
```

### Article Editing
```
GET /publishers/{handle}/articles/{slug} → returns { markdown: "---\n...\n---\n# Body" } →
Parse YAML frontmatter into form fields → parse body into Tiptap document →
User edits → serialize back → PATCH with { markdown: "..." }
```

### Article Purchase
```
User on /articles/[slug] → clicks Purchase →
GET /articles/{slug}/context (no auth) → 402 + WWW-Authenticate challenge →
Parse challenge → sign with wallet → retry with WalletProof header →
200 + ContextPackage + Payment-Receipt header →
Render full article body
```

## Backend Changes Required

The current backend serves AI agents — the `/articles/{slug}/context` endpoint returns a `ContextPackage` (summary, key_claims, excerpts, citation) but NOT the full article body. Human consumers need the rendered body after payment.

**Required**: A new endpoint or modification so that after a verified purchase, the consumer can retrieve the full article body. Options:
1. Add a `body` field to the context package response (simplest, but mixes agent and human concerns)
2. New endpoint `GET /articles/{slug}/body` that checks `one_time_purchases` for the caller's wallet and returns the markdown body if purchased

Option 2 is cleaner — keeps the agent context package focused and gives the frontend a dedicated endpoint. The endpoint should return `{body: "markdown content"}` and 402 if not purchased.

Additionally, the repo restructure (moving backend into `backend/`) will require updating import paths in `alembic.ini`, any CI scripts, and the `CLAUDE.md` instructions.

## Verification

1. **Backend restructure**: Move `app/`, `migrations/`, `tests/`, `pyproject.toml`, `alembic.ini`, `articles/` into `backend/`. Verify backend still starts and tests pass from `backend/` directory.
2. **Frontend scaffold**: `npx create-next-app@latest web` with TypeScript, Tailwind, App Router. Install Privy, wagmi, viem, Tiptap, TanStack Query.
3. **Login flow**: Connect via Privy → challenge/sign → verify `WalletProof` header works against backend.
4. **Publisher dashboard**: Create publisher via API → see it in dashboard → navigate to editor.
5. **Article creation**: Fill metadata form + write in Tiptap → save draft → verify markdown roundtrips correctly (YAML frontmatter + body intact).
6. **Article publishing**: Fill all required fields → click Publish → verify article appears in home feed.
7. **Article purchase**: As a different wallet, view article → see paywall → purchase → see full body.
8. **Markdown fidelity**: Create article with headings, blockquotes, code blocks, lists, links → save → reload → verify formatting preserved.

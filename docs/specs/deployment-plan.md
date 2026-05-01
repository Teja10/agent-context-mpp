# Thoth Deployment Plan

## Summary

Thoth should go live in two tracks:

- A public testnet deployment that proves the current FastAPI app can run behind
  a real URL and emit the expected MPP payment challenge.
- A production deployment for the target Next.js frontend, FastAPI backend, and
  Postgres-backed marketplace.

The recommended first production topology is:

- Frontend: Vercel-hosted Next.js.
- Backend API: Render web service running FastAPI.
- Database: Render Postgres in the same region as the backend.
- Domains: separate frontend and API hostnames.
- Payments: Tempo/MPP testnet in staging, Tempo/MPP mainnet only after explicit
  production safety checks pass.

This is intentionally not Kubernetes, ECS, or a broad platform build. The goal
is to get a reliable product online with managed primitives, then migrate to
AWS only when the operational control is worth the extra infrastructure.

## Deployment Goals

- Make the current demo reachable at a public testnet URL.
- Support the future production web app without changing the product
  architecture.
- Keep frontend, backend, and database environments clearly separated.
- Keep Tempo testnet and mainnet configuration impossible to confuse.
- Preserve the backend as the entitlement source of truth.
- Make deployments repeatable enough to become Linear milestones.

## Recommended Topology

### Staging

- Frontend: Vercel preview/staging deployment.
- Backend: Render web service.
- Database: Render Postgres staging instance.
- Tempo network: testnet.
- Domains:
  - `staging.thoth.so`.
  - `api-staging.thoth.so`.

### Production

- Frontend: Vercel production deployment.
- Backend: Render web service.
- Database: Render Postgres production instance.
- Tempo network: mainnet only after explicit confirmation.
- Domains:
  - `thoth.so`.
  - `api.thoth.so`.

## Why This Topology

Vercel is the default fit for the planned Next.js frontend because it supports
Git-based deployments, preview URLs, and managed Next.js behavior.

Render is the default fit for the FastAPI backend because it supports Python web
services, Docker services, managed Postgres, private networking between services
in the same region, custom domains, and zero-downtime deploys.

AWS remains a valid later target, but App Runner plus private RDS adds VPC
connector and outbound internet design work. Since the backend must reach public
Tempo RPC endpoints while also reaching a private database, AWS requires more
networking decisions before it is simpler than a managed PaaS.

## Environment Model

### Local

Purpose: developer work.

Runtime:

- FastAPI started with `uv run uvicorn`.
- Next.js started with the package manager chosen when frontend is added.
- Local Postgres once production persistence exists.
- Tempo testnet only.

Rules:

- `.env` is local only.
- Never point local frontend at production backend by default.
- Never use production MPP secrets locally.

### Preview

Purpose: frontend review per pull request.

Runtime:

- Vercel preview deployment.
- Usually points at staging backend.

Rules:

- Preview must not point at production backend unless intentionally configured
  for a release candidate.
- Preview environment variables must be distinct from production.

### Staging

Purpose: full-stack integration and Tempo testnet validation.

Runtime:

- Vercel staging alias or branch deployment.
- Render staging backend.
- Render staging Postgres.
- Tempo testnet.

Rules:

- Staging database can be reset.
- Staging must have realistic publisher/article/payment test data.
- Staging must run the real MPP payment challenge path.

### Production

Purpose: real users and real payments.

Runtime:

- Vercel production frontend.
- Render production backend.
- Render production Postgres.
- Tempo mainnet.

Rules:

- Mainnet requires `ENVIRONMENT=production`.
- Mainnet requires `MAINNET_CONFIRMATION=true`.
- Mainnet `MPP_REALM` must be the production API domain, not localhost or a
  staging domain.
- Production database must not be reset except through an explicit recovery
  operation.

## Service Contracts

### Frontend Service

Platform: Vercel.

Build:

- Build command: use the frontend package manager once chosen.
- Output: standard Next.js output.

Required environment variables:

- `NEXT_PUBLIC_API_BASE_URL`.
- `NEXT_PUBLIC_THOTH_ENVIRONMENT`.
- `NEXT_PUBLIC_TEMPO_NETWORK`.

Forbidden frontend environment variables:

- `MPP_SECRET_KEY`.
- `DATABASE_URL`.
- Private Tempo keys.
- Publisher private keys.
- Raw payment authorization secrets.

Deploy gates:

- Typecheck.
- Lint.
- Production build.
- Browser smoke for home, search, article preview, locked article, unlocked
  article, account, and publisher workspace once those routes exist.

### Backend Service

Platform: Render web service.

Start command for the current FastAPI shape:

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
```

Production can later move to a process manager if needed, but the first deploy
should keep the runtime simple.

Required environment variables:

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

Current runtime:

- The backend requires Postgres through `DATABASE_URL`.
- Migrations must run before service startup.

Deploy gates:

- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run pyright`
- `uv run pytest`
- Database migrations pass before service start once migrations exist.

### Database Service

Platform: Render Postgres.

Staging:

- Small managed Postgres instance.
- Backups useful but not release-blocking.
- Reset allowed with explicit action.

Production:

- Separate managed Postgres instance.
- Automated backups enabled.
- Point-in-time recovery or provider-equivalent recovery must be enabled before
  mainnet payments.
- Access through internal/private connection from backend where available.

Rules:

- Frontend never connects to Postgres.
- Database credentials live only in backend environment configuration.
- Schema changes run through migrations, not ad hoc startup DDL.

## Domain And Routing

Required domains:

- Frontend staging: `staging.thoth.so`.
- Backend staging: `api-staging.thoth.so`.
- Frontend production: `thoth.so`.
- Backend production: `api.thoth.so`.

Backend CORS:

- Staging allows only the staging frontend domain and approved preview domains.
- Production allows only the production frontend domain.
- No wildcard CORS in production.

MPP realm:

- Staging realm: `api-staging.thoth.so`.
- Production realm: `api.thoth.so`.

The realm must match the public API host that agents and payment clients use.

## Deployment Phases

### Phase 0: Public Testnet Demo

Goal: get the current FastAPI app publicly reachable without claiming
production durability.

Tasks:

- Create a Render staging web service from the repo.
- Configure Python 3.12 and `uv sync`.
- Run `uv run alembic upgrade head`.
- Start with `uv run uvicorn app.main:app --host 0.0.0.0 --port "$PORT"`.
- Set testnet environment variables from `.env.example`.
- Set `DATABASE_URL` to the staging Postgres connection string.
- Set `MPP_REALM` to the Render or staging API domain.
- Confirm `/health` returns ok.
- Confirm `/articles` returns the demo articles.
- Confirm unauthenticated `/articles/ai-agent-payments/context` returns `402`
  with `WWW-Authenticate`.
- Complete Tempo wallet readiness and run a real testnet `tempo request`.

Exit criteria:

- Public URL exists.
- 402 challenge is visible over HTTPS.
- Testnet paid request works or the wallet/funding blocker is documented with
  exact failing command and output.

### Phase 1: Production Persistence Foundation

Goal: make the backend deployable as a durable app.

Tasks:

- Add Postgres dependency and migration tool.
- Require `DATABASE_URL`.
- Add migrations for publishers, articles, purchases, subscriptions, usage
  events, and feedback.
- Add `/health/live` and `/health/ready`.
- Add `CORS_ORIGINS`.
- Add structured startup config validation.
- Provision Render staging Postgres.
- Run migrations in staging before service startup.

Exit criteria:

- Staging backend uses Postgres.
- Service restart preserves purchases and articles.
- Readiness fails when database config is invalid.
- Wildcard CORS is gone outside local development.

### Phase 2: Frontend Public App

Goal: deploy the human-facing web experience.

Tasks:

- Create the Next.js app.
- Configure Vercel project.
- Set `NEXT_PUBLIC_API_BASE_URL` to staging API.
- Implement discovery, publisher, article preview, and locked article states.
- Add preview deployments for pull requests.
- Add staging domain.

Exit criteria:

- Public staging frontend can browse article previews.
- Locked article state calls backend and handles payment-required responses.
- Preview deployment exists for a frontend PR.

### Phase 3: Paid Access And Subscriptions

Goal: support PPV and per-publisher subscription flows in staging.

Tasks:

- Implement PPV entitlement persistence.
- Implement subscription persistence.
- Wire frontend PPV and subscription CTAs to backend payment flows.
- Record receipts.
- Record usage events after paid Markdown/context access.
- Add useful/not-useful feedback.

Exit criteria:

- PPV unlocks one article.
- Publisher subscription unlocks subscriber-accessible articles for that
  publisher only.
- Search results reflect access state.
- Feedback requires entitlement.

### Phase 4: Production Launch

Goal: cut production over to mainnet.

Tasks:

- Provision production Render backend.
- Provision production Render Postgres.
- Provision production Vercel deployment.
- Configure production domains.
- Configure production CORS.
- Configure production MPP realm.
- Set `TEMPO_NETWORK=mainnet`.
- Set `ENVIRONMENT=production`.
- Set `MAINNET_CONFIRMATION=true`.
- Run migrations.
- Run production smoke tests.

Exit criteria:

- Production frontend is live.
- Production backend readiness is healthy.
- Production API returns expected previews.
- Mainnet paid path is verified with a low-value purchase.
- Receipts are stored in production Postgres.

## Smoke Tests

### Backend Staging

```bash
curl -fsS https://api-staging.thoth.so/health
curl -fsS https://api-staging.thoth.so/articles
curl -i https://api-staging.thoth.so/articles/ai-agent-payments/context
```

Expected:

- Health returns ok.
- Articles returns public metadata.
- Context endpoint returns `402 Payment Required` without authorization.

### Tempo Testnet

```bash
tempo wallet whoami
tempo request GET https://api-staging.thoth.so/articles/ai-agent-payments/context
```

Expected:

- Wallet is ready.
- Request completes payment on testnet.
- Backend returns paid context and records receipt.

### Frontend Staging

Browser checks:

- Home loads.
- Article preview loads.
- Locked article shows PPV and subscription choices.
- Payment-required response is displayed as a locked state, not a crash.
- Unlocked article renders Markdown after entitlement.

## Observability

Backend logs must include:

- Request ID.
- Route.
- Status code.
- Publisher ID or handle when available.
- Article ID or slug when available.
- Payment reference when available.
- Entitlement decision: preview, PPV, subscription, denied.

Backend logs must not include:

- `Authorization` header.
- `MPP_SECRET_KEY`.
- Private keys.
- Full receipt payloads if they ever contain sensitive material.
- Full paid Markdown body.

Metrics to add once traffic exists:

- Payment challenge count.
- Successful PPV purchase count.
- Successful subscription count.
- Paid Markdown access count.
- Paid context access count.
- Search request count.
- Search-to-purchase conversion.
- Useful/not-useful feedback rate.

## Backup And Recovery

Staging:

- Backups are useful for debugging but not product-critical.
- Reset is allowed with explicit approval.

Production:

- Automated Postgres backups required.
- Recovery process must be documented before mainnet launch.
- Database migrations must be reversible through backup restore, not by hoping
  down migrations are enough.
- Production deploys that include migrations need a pre-deploy backup or
  provider snapshot when the migration is destructive.

## Security Requirements

- No secrets in frontend runtime variables.
- No secrets committed to the repo.
- Production CORS has no wildcard origins.
- Admin/publisher mutation APIs require wallet ownership authorization.
- Payment callbacks or receipt confirmations must verify wallet, article,
  amount, currency, network, and publisher.
- Mainnet startup hard-fails when safety config is missing or local/staging
  realms are configured.
- Staging and production secrets are separate.

## Cost Notes

This document intentionally avoids locking exact monthly prices into the spec
because provider prices change. Before creating Linear issues that include
budget commitments, check current provider pricing.

Current provider facts checked while writing this plan:

- Render web service plans start with small paid instances and support Docker,
  Python web services, managed Postgres, and private networking.
- Vercel supports Git-based Next.js deployments, preview deployments, and
  environment variables per environment.
- AWS App Runner can run a container or source-backed web app, but private RDS
  access requires VPC connector design; external Tempo RPC access then needs a
  public egress plan such as NAT.

## AWS Migration Path

Move to AWS when one of these becomes true:

- Compliance requires AWS-native controls.
- Render cost or scaling becomes worse than managed AWS complexity.
- The team needs VPC-level private networking and IAM integration.
- Multi-region infrastructure becomes a requirement.

AWS target shape:

- Frontend: Vercel can remain, or migrate to AWS Amplify/CloudFront later.
- Backend: AWS App Runner or ECS Fargate.
- Database: Amazon RDS for PostgreSQL.
- Secrets: AWS Secrets Manager or SSM Parameter Store.
- Logs and metrics: CloudWatch.
- Domains: Route 53 plus managed TLS.

Important AWS caveat:

If App Runner connects to private RDS through a VPC connector, outbound traffic
is routed through the VPC. Since Thoth must also reach public Tempo RPC
endpoints, the AWS design needs NAT or equivalent public egress. This is the
main reason AWS is not the default first live path.

## Linear Milestone Candidates

### Deployment M1: Public Testnet API

Deliverables:

- Render staging backend.
- Public staging API domain.
- Testnet environment configuration.
- Public 402 challenge smoke test.

Acceptance criteria:

- `/health` succeeds over HTTPS.
- `/articles` succeeds over HTTPS.
- Paid context endpoint emits expected `402`.
- Tempo testnet paid request is either successful or blocked only by documented
  wallet/funding state.

### Deployment M2: Durable Backend Runtime

Deliverables:

- Postgres-backed staging backend.
- Migration command.
- Readiness endpoint.
- Restricted CORS.

Acceptance criteria:

- Service restart preserves data.
- Migrations run before deploy.
- Readiness fails when database is unreachable.
- Wildcard CORS is removed outside local development.

### Deployment M3: Staging Frontend

Deliverables:

- Vercel project.
- Staging frontend domain.
- Preview deploys.
- API base URL environment wiring.

Acceptance criteria:

- Frontend preview deploy is created for a PR.
- Staging frontend talks to staging backend.
- Locked payment state renders cleanly.

### Deployment M4: Production Launch

Deliverables:

- Production frontend.
- Production backend.
- Production Postgres.
- Production domains.
- Mainnet configuration.

Acceptance criteria:

- Production readiness is healthy.
- Mainnet safety checks pass.
- Low-value mainnet PPV purchase succeeds.
- Receipt persists in production Postgres.

## References

- Vercel Next.js deployments: https://vercel.com/docs/frameworks/nextjs
- Vercel environment variables: https://vercel.com/docs/environment-variables
- Render FastAPI deployment: https://render.com/docs/deploy-fastapi
- Render web services: https://render.com/docs/web-services
- Render private networking: https://render.com/docs/private-network
- Render Postgres: https://render.com/docs/postgresql
- Render regions: https://render.com/docs/regions
- AWS App Runner overview: https://docs.aws.amazon.com/apprunner/latest/dg/what-is-apprunner.html
- AWS App Runner VPC access: https://docs.aws.amazon.com/apprunner/latest/dg/network-vpc.html
- Amazon RDS for PostgreSQL pricing: https://aws.amazon.com/rds/postgresql/pricing/

# agent-context-mpp

Thoth is a FastAPI API for paid machine-readable article context. It serves
public article metadata for humans and agents, then protects structured context
packages behind MPP payment challenges once articles exist in Postgres.

The included configuration targets Tempo moderato/testnet through
`.env.example`.

## Prerequisites

- Python 3.12 or newer
- uv
- tempo CLI
- Postgres 16

Check tempo wallet readiness with:

```bash
tempo wallet whoami
```

## Setup

```bash
git clone https://github.com/Teja10/agent-context-mpp.git
cd agent-context-mpp
uv sync
cp .env.example .env
```

Review `.env` before starting the server. The example file uses
`TEMPO_NETWORK=moderato`, `MAINNET_CONFIRMATION=false`, and the testnet
currency address used by the demo. `DATABASE_URL` is required and must use the
`postgresql+psycopg` SQLAlchemy scheme.

Run migrations before starting the server:

```bash
uv run alembic upgrade head
```

## Run Server

```bash
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Fresh migrations create schema only. Article creation is owned by a later
publisher workflow, so a new database has no paid article route to demo yet.

## Tests

```bash
uv run ruff format --check .
uv run ruff check .
uv run pyright
DATABASE_URL=postgresql+psycopg://thoth:thoth@127.0.0.1:55432/thoth_test uv run alembic upgrade head
DATABASE_URL=postgresql+psycopg://thoth:thoth@127.0.0.1:55432/thoth_test uv run pytest
```

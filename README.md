# agent-context-mpp

Thoth is a FastAPI demo for paid machine-readable article context. It
serves public article metadata for humans and agents, then protects the
structured context package behind an MPP payment challenge.

The included demo targets Tempo moderato/testnet through `.env.example`. The
paid request step requires a funded Tempo wallet.

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

## Testnet Demo

Use two terminals.

Terminal 1 runs the API server:

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Terminal 2 runs the demo script:

```bash
./scripts/demo_testnet.sh
```

The script checks the wallet, shows the raw 402 payment challenge from `curl`,
then repeats the request with `tempo request`.

## Tests

```bash
uv run ruff format --check .
uv run ruff check .
uv run pyright
DATABASE_URL=postgresql+psycopg://thoth:thoth@127.0.0.1:55432/thoth_test uv run alembic upgrade head
DATABASE_URL=postgresql+psycopg://thoth:thoth@127.0.0.1:55432/thoth_test uv run pytest
```

# Polymarket Intelligence

A full-stack system for screening Polymarket events, running LLM-driven market analysis, producing bet decisions, and optionally placing orders on the Polymarket CLOB. It ships with a JWT-protected dashboard, a LangGraph execution pipeline, schedulers, and accounting for both paper and live bankrolls.

---

## The idea

Polymarket lists many event markets with different liquidity and time horizons. This project turns repeated research into a **single graph**: **screen → rank → top-N → parallel deep-dive per market → aggregate decisions → execute (or dry-run)**. Prompts, risk knobs, and credentials live in the database and environment so you can change behaviour without redeploying code.

**Safety default:** seeded settings keep **`betting.execution_enabled` off**. Bets are stored as `dry_run` until you explicitly enable live execution and supply Polymarket CLOB credentials. That is intentional, not a demo limitation.

---

## Key features

### LangGraph pipeline

- **screen_markets** — initial universe filter using API data and rules.
- **rank_markets** — score and order candidates (`top_n` comes from settings).
- **select_top_n** — take the best N for expensive analysis.
- **analyze_market** — fan-out: one analysis subgraph per market (parallel `Send`).
- **decide_all** — fold analyses into coordinated decisions.
- **execute_bets** — persist bets and, when execution is on, talk to the CLOB.

Flow:

```
screen_markets → rank_markets → select_top_n
        │
        └─► analyze_market (×N, parallel)
                    │
                    ▼
            decide_all → execute_bets → END
```

### Dashboard

- Overview metrics, pipeline run history, per-run drill-down.
- Bets view, rich **Settings** (prompts, risk, execution toggles).
- React Query, protected routes, toast notifications.

### Data plane

- **PostgreSQL** — markets, runs, analyses, decisions, bets, wallet snapshots, execution audit trail.
- **Qdrant** — vector store; backend uses **sentence-transformers** for embeddings.
- **APScheduler** — background scheduling and polling (see `scheduler_service`).

### LLMs

- **Anthropic** and **Yandex Cloud** (chat completions; optional Yandex web search). Provider choice is configuration-driven.
- More detail on adapters and prompt wiring: [`backend/app/llm/README.md`](backend/app/llm/README.md).

### Trading and risk

- Optional **py-clob-client** integration (extra dependency).
- Kelly-style sizing and configurable bankroll sources (including paper bankroll for dry-run).

---

## Tech stack

| Layer | Technologies |
|-------|----------------|
| Backend | Python 3.12+, FastAPI, Uvicorn, SQLAlchemy 2 (async), Alembic |
| Agent graph | LangGraph, LangChain Core |
| Frontend | React 18, TypeScript, Vite 5, Tailwind CSS, TanStack Query, Recharts |
| Data | PostgreSQL 16, Qdrant |
| Ops | Docker, Docker Compose |

---

## Architecture

- **`backend/app`** — routers (`api/`), services (`services/`), ORM models (`models/`), Polymarket integrations (`core/`), LangGraph (`graph/`).
- **`frontend/src`** — `pages/`, shared `components/`, `api/client`.
- **`docker-compose.yml`** — Postgres + Qdrant + backend (Alembic migrate + seed on `entrypoint.sh`) + Vite dev container.
- **`docker-compose.dev.yml`** — overlay: backend `--reload`, frontend on **5173**.

Typical request path:

1. User signs in → JWT issued.
2. SPA calls `/api/v1/...`.
3. Pipeline creates a `PipelineRun`, advances `current_stage`, writes analyses / decisions / bets.
4. If live trading is on, orders flow through execution services and DB-backed pollers.

Interactive API docs (when backend is up): `http://localhost:8000/api/docs`.

---

## Getting started (Docker)

### Prerequisites

- Docker 20.10+ and Compose v2
- At least one LLM provider key for non-trivial analysis runs

### Environment

Copy [`.env.example`](.env.example) to **`.env`** at the repo root and fill in. With `docker compose`, variables are injected into the backend container from that file via Compose interpolation (see `docker-compose.yml` `environment:`); the app also loads the repo-root `.env` when you run the backend locally from a checkout (see `app/config.py`).

| Group | Purpose |
|-------|---------|
| `POSTGRES_PASSWORD` | DB password for the `poly` user in Compose |
| `AUTH_SECRET_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD` | JWT signing + first dashboard user |
| `CORS_ORIGINS` | Optional; comma-separated browser origins (defaults cover local Vite ports) |
| `ANTHROPIC_API_KEY` | Claude |
| `YANDEX_*` | Yandex LLM / Search when used |
| `POLYMARKET_*` | Wallet + CLOB API — **only if you want live orders** (`POLYMARKET_PROXY_ADDRESS` for proxy/email wallets) |

### Run

```bash
docker compose up -d --build
```

| Service | URL |
|---------|-----|
| Frontend (Vite in container) | http://localhost:3000 |
| Backend | http://localhost:8000 |
| Postgres | `localhost:5432` (database `polymarket`, user `poly`) |
| Qdrant | http://localhost:6333 |

Dev overlay (Vite on **5173**, uvicorn `--reload`):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

Frontend then: http://localhost:5173

---

## Local development (no full stack in Docker)

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -e .
pip install -e ".[clob]"   # only for live CLOB
```

Start only infra:

```bash
docker compose up -d db qdrant
```

Point `DATABASE_URL`, `DATABASE_URL_SYNC`, and `QDRANT_URL` in `.env` at those services, then:

```bash
alembic upgrade head
python -m app.bootstrap.seed
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Set `VITE_API_PROXY_TARGET` to your backend URL (see `vite.config.ts` and Compose env).

---

## Configuration

- Secrets and DSNs: **`.env`** at repo root (optional `backend/.env`).
- Runtime behaviour (limits, execution flags, bankroll, prompt text) is largely in **seeded DB settings** after `python -m app.bootstrap.seed`; some fields mirror env (`app/config.py`, `settings_service`).
- CORS: comma-separated `CORS_ORIGINS` (defaults include `http://localhost:3000` and `http://localhost:5173`).

---

## API overview

Protected resources live under `/api/v1/` (except health and docs).

| Tag | Responsibility |
|-----|----------------|
| `auth` | Login, JWT |
| `pipeline` | Start runs, status |
| `markets` | Market data |
| `decisions` | Decisions per run |
| `bets` | Bet ledger (`exclude_dry_run` query flag) |
| `settings`, `prompts` | Tunables and prompt bodies |
| `scheduler` | Cron-like automation |
| `dashboard`, `stats` | Aggregated analytics |
| `wallet` | Balances / wallet state |
| `system` | Operational endpoints |

Health: `GET /api/health`

---

## Project structure

```text
.
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── graph/
│   │   ├── llm/
│   │   ├── models/
│   │   ├── services/
│   │   ├── clob/
│   │   ├── config.py
│   │   └── main.py
│   ├── alembic/
│   ├── Dockerfile
│   ├── entrypoint.sh
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   └── package.json
├── docker-compose.yml
├── docker-compose.dev.yml
├── .env.example
└── README.md
```

---

## Limitations and disclaimer

- Polymarket and derivatives of prediction markets are subject to **platform terms and local law**. This software is **not** financial or legal advice.
- Signal quality depends on prompts, API data freshness, and risk parameters; validate with paper mode before risking capital.
- External APIs (Polymarket, LLM vendors) can rate-limit or fail mid-run.
- `docker-compose.yml` bind-mounts `./backend` for developer ergonomics — use an image-only deploy profile for production.

---

## Optional CLOB install

Live trading requires the optional extra from [`backend/pyproject.toml`](backend/pyproject.toml):

```bash
pip install -e ".[clob]"
```

---

## Possible improvements

1. Production Compose without source bind-mounts; inject secrets from a vault or CI OIDC.
2. Integration tests for the graph with stubbed Polymarket + LLM HTTP.
3. Centralised retry/backoff policy for all outbound HTTP clients.
4. Prometheus metrics and structured JSON logging for long-running cloud workers.

---

## Dependencies

Backend: see [`backend/pyproject.toml`](backend/pyproject.toml). Notable libraries: FastAPI, SQLAlchemy, Alembic, LangGraph, Anthropic SDK, Qdrant client, sentence-transformers, APScheduler 3.x.

Frontend: see [`frontend/package.json`](frontend/package.json) — React, Vite, Tailwind, TanStack Query, Recharts.

There is no root `LICENSE` file in this repo yet; add one if you open-source the project.

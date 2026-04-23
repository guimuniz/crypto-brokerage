# Crypto Brokerage Platform

A cryptocurrency brokerage platform built with **FastAPI**, demonstrating clean architecture, double-entry accounting, idempotent trading, and resilient integrations.

## Stack

| Layer | Technology |
|---|---|
| Web Framework | FastAPI + Uvicorn |
| Database | PostgreSQL 16 (asyncpg) |
| ORM / Migrations | SQLAlchemy 2.0 (async) + Alembic |
| Validation | Pydantic v2 |
| Authentication | JWT (python-jose + passlib/bcrypt) |
| HTTP Client | httpx |
| Resilience | tenacity (retry with backoff) |
| Package Manager | uv |
| Containerization | Docker + Docker Compose |

## Architecture

```
API Layer (app/api/)          → Routes, schemas, dependency injection
Service Layer (app/services/) → Business rules / use cases
Repository Layer (app/repos/) → Data access (async SQLAlchemy)
Integration Layer (app/integ.)→ External gateways (Exchange, Banking)
Model Layer (app/models/)     → SQLAlchemy 2.0 models
Core (app/core/)              → Config, DB, security, exceptions
```

Endpoints are versioned under `/api/v1` and organized into:

- **Auth** — registration, login, token refresh
- **Accounts** — account creation and retrieval
- **Trading** — buy/sell order creation
- **Portfolio** — positions and balance queries

> For full architecture details, see [ARCHITECTURE.md](ARCHITECTURE.md).

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)
- (Optional for local development) Python 3.12+ and [uv](https://github.com/astral-sh/uv)

## Quick Start with Docker

### 1. Clone the repository

```bash
git clone https://github.com/guilherme-castro-braza/crypto-brokerage.git
cd crypto-brokerage
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` as needed. Available variables:

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://brokerage:brokerage@localhost:5432/brokerage` |
| `JWT_SECRET_KEY` | Secret key for JWT tokens | `CHANGE_ME...` |
| `ENVIRONMENT` | `development` / `staging` / `production` | `development` |
| `DEBUG` | Debug mode | `false` |
| `EXCHANGE_API_URL` | Exchange API URL | — |
| `EXCHANGE_API_KEY` | Exchange API key | — |
| `EXCHANGE_API_SECRET` | Exchange API secret | — |
| `BANKING_API_URL` | Banking API URL | — |
| `BANKING_API_KEY` | Banking API key | — |

### 3. Start the containers

```bash
docker compose up --build -d
```

This starts three services:

| Service | Description | Port |
|---|---|---|
| **db** | PostgreSQL 16 (Alpine) | `5432` |
| **migrate** | Runs `alembic upgrade head` and exits | — |
| **api** | Uvicorn serving the FastAPI app | `8000` |

### 4. Access the API

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Local Development (without Docker)

```bash
# Install dependencies (including dev)
uv sync

# Start a PostgreSQL instance (e.g. via Docker)
docker compose up db -d

# Run migrations
alembic upgrade head

# Start the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Useful Commands

```bash
# View API logs
docker compose logs -f api

# Stop all containers
docker compose down

# Stop and remove volumes (clears the database)
docker compose down -v

# Run linter
uv run ruff check .

# Run type checker
uv run mypy app/

# Run tests
uv run pytest
```

## Project Structure

```
crypto-brokerage/
├── app/
│   ├── main.py              # App factory, lifespan, exception handlers
│   ├── api/
│   │   ├── deps.py          # Dependency injection (FastAPI Depends)
│   │   ├── schemas/         # Pydantic v2 request/response models
│   │   └── v1/              # Versioned route handlers
│   ├── services/            # Business logic
│   ├── repositories/        # Data access (async)
│   ├── models/              # SQLAlchemy 2.0 models
│   ├── integrations/        # External gateways (ABC + implementations)
│   ├── events/              # Domain events
│   └── core/                # Config, database, security, exceptions
├── alembic/                 # Database migrations
├── docker-compose.yml       # Service orchestration
├── Dockerfile               # Multi-stage build (builder + runtime)
├── pyproject.toml           # Dependencies and tool configuration
└── ARCHITECTURE.md          # Detailed architecture documentation
```

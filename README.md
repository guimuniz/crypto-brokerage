# Crypto Brokerage Platform

Plataforma de corretora de criptomoedas construída com **FastAPI**, demonstrando arquitetura limpa, contabilidade de dupla entrada (_double-entry accounting_), trading idempotente e integrações resilientes.

## Stack

| Camada | Tecnologia |
|---|---|
| Framework Web | FastAPI + Uvicorn |
| Banco de Dados | PostgreSQL 16 (asyncpg) |
| ORM / Migrations | SQLAlchemy 2.0 (async) + Alembic |
| Validação | Pydantic v2 |
| Autenticação | JWT (python-jose + passlib/bcrypt) |
| HTTP Client | httpx |
| Resiliência | tenacity (retry com backoff) |
| Gerenciador de pacotes | uv |
| Containerização | Docker + Docker Compose |

## Arquitetura

```
API Layer (app/api/)          → Rotas, schemas, dependency injection
Service Layer (app/services/) → Regras de negócio / use cases
Repository Layer (app/repos/) → Acesso a dados (async SQLAlchemy)
Integration Layer (app/integ.)→ Gateways externos (Exchange, Banking)
Model Layer (app/models/)     → Modelos SQLAlchemy 2.0
Core (app/core/)              → Config, DB, segurança, exceções
```

Os endpoints estão versionados em `/api/v1` e organizados em:

- **Auth** — registro, login, refresh token
- **Accounts** — criação e consulta de contas
- **Trading** — criação de ordens de compra/venda
- **Portfolio** — consulta de posições e saldo

> Para detalhes completos da arquitetura, veja [ARCHITECTURE.md](ARCHITECTURE.md).

## Pré-requisitos

- [Docker](https://docs.docker.com/get-docker/) e [Docker Compose](https://docs.docker.com/compose/install/)
- (Opcional para desenvolvimento local) Python 3.12+ e [uv](https://github.com/astral-sh/uv)

## Início rápido com Docker

### 1. Clone o repositório

```bash
git clone https://github.com/guilherme-castro-braza/crypto-brokerage.git
cd crypto-brokerage
```

### 2. Configure as variáveis de ambiente

```bash
cp .env.example .env
```

Edite o `.env` conforme necessário. As variáveis disponíveis são:

| Variável | Descrição | Default |
|---|---|---|
| `DATABASE_URL` | String de conexão PostgreSQL | `postgresql+asyncpg://brokerage:brokerage@localhost:5432/brokerage` |
| `JWT_SECRET_KEY` | Chave secreta para tokens JWT | `CHANGE_ME...` |
| `ENVIRONMENT` | `development` / `staging` / `production` | `development` |
| `DEBUG` | Modo debug | `false` |
| `EXCHANGE_API_URL` | URL da API da exchange | — |
| `EXCHANGE_API_KEY` | Chave da API da exchange | — |
| `EXCHANGE_API_SECRET` | Secret da API da exchange | — |
| `BANKING_API_URL` | URL da API bancária | — |
| `BANKING_API_KEY` | Chave da API bancária | — |

### 3. Suba os containers

```bash
docker compose up --build -d
```

Isso inicia três serviços:

| Serviço | Descrição | Porta |
|---|---|---|
| **db** | PostgreSQL 16 (Alpine) | `5432` |
| **migrate** | Executa `alembic upgrade head` e encerra | — |
| **api** | Uvicorn servindo a FastAPI | `8000` |

### 4. Acesse a API

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Desenvolvimento local (sem Docker)

```bash
# Instale as dependências (incluindo dev)
uv sync

# Suba um PostgreSQL (ex: via Docker)
docker compose up db -d

# Execute as migrations
alembic upgrade head

# Inicie o servidor
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Comandos úteis

```bash
# Ver logs da API
docker compose logs -f api

# Parar todos os containers
docker compose down

# Parar e remover volumes (limpa o banco)
docker compose down -v

# Executar linter
uv run ruff check .

# Executar type checker
uv run mypy app/

# Executar testes
uv run pytest
```

## Estrutura do projeto

```
crypto-brokerage/
├── app/
│   ├── main.py              # App factory, lifespan, exception handlers
│   ├── api/
│   │   ├── deps.py          # Dependency injection (FastAPI Depends)
│   │   ├── schemas/         # Pydantic v2 request/response models
│   │   └── v1/              # Rotas versionadas
│   ├── services/            # Lógica de negócio
│   ├── repositories/        # Acesso a dados (async)
│   ├── models/              # Modelos SQLAlchemy 2.0
│   ├── integrations/        # Gateways externos (ABC + implementações)
│   ├── events/              # Eventos de domínio
│   └── core/                # Config, database, security, exceptions
├── alembic/                 # Migrations do banco de dados
├── docker-compose.yml       # Orquestração dos serviços
├── Dockerfile               # Build multi-stage (builder + runtime)
├── pyproject.toml           # Dependências e configuração de ferramentas
└── ARCHITECTURE.md          # Documentação detalhada da arquitetura
```

## Licença

Este projeto é um demo de arquitetura e não possui licença aberta definida.

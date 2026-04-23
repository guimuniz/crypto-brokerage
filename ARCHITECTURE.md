# Architecture — Crypto Brokerage Platform

## 1. Component Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                          FastAPI Application                          │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │  API Layer  (app/api/)                                        │    │
│  │  v1/auth · v1/accounts · v1/trading · v1/portfolio           │    │
│  │  schemas/ (Pydantic v2)  ·  deps.py (DI)                    │    │
│  └────────────────────────┬─────────────────────────────────────┘    │
│                           │                                          │
│  ┌────────────────────────▼─────────────────────────────────────┐    │
│  │  Service Layer  (app/services/)                               │    │
│  │  OnboardingService · BankingService · TradingService          │    │
│  │  PortfolioService                                             │    │
│  └───────────┬───────────────────────────────┬──────────────────┘    │
│              │                               │                       │
│  ┌───────────▼──────────────┐   ┌───────────▼──────────────────┐    │
│  │  Repository Layer        │   │  Integration Layer            │    │
│  │  (app/repositories/)     │   │  (app/integrations/)          │    │
│  │  UserRepository          │   │  ExchangeGateway (ABC)        │    │
│  │  AccountRepository       │   │  BankingGateway  (ABC)        │    │
│  │  OrderRepository         │   │  HttpExchangeGateway          │    │
│  │  LedgerRepository        │   │  HttpBankingGateway           │    │
│  │  TransactionRepository   │   │  StubExchangeGateway          │    │
│  │  PositionRepository      │   │  StubBankingGateway           │    │
│  └───────────┬──────────────┘   └──────────────────────────────┘    │
│              │                                                       │
│  ┌───────────▼──────────────────────────────────────────────────┐    │
│  │  Data Model Layer  (app/models/ — SQLAlchemy 2.0)            │    │
│  │  User · UserProfile · Account · BankAccount · Asset          │    │
│  │  Order · TradeExecution · Position · Transaction             │    │
│  │  LedgerEntry  ← source of financial truth                    │    │
│  └───────────┬──────────────────────────────────────────────────┘    │
│              │                                                       │
│  ┌───────────▼──────────────────────────────────────────────────┐    │
│  │  Core  (app/core/)                                           │    │
│  │  config.py · database.py · security.py · exceptions.py       │    │
│  └──────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
        │                              │
        ▼                              ▼
  PostgreSQL                   External APIs
  (asyncpg)                    Exchange · Banking
```

## 2. Directory Structure

```
crypto-brokerage/
├── app/
│   ├── main.py                  # FastAPI app factory, lifespan, exception handlers
│   ├── api/
│   │   ├── deps.py              # FastAPI dependency injection
│   │   ├── schemas/             # Pydantic v2 request/response models
│   │   └── v1/                  # Route handlers (auth, accounts, trading, portfolio)
│   ├── services/                # Business logic / use cases
│   ├── repositories/            # Data access abstraction (async SQLAlchemy)
│   ├── models/                  # SQLAlchemy 2.0 mapped_column models
│   ├── integrations/            # External gateway ABCs + HTTP/stub implementations
│   ├── events/                  # Domain event definitions
│   └── core/                    # Config, DB session, security, exceptions
├── alembic/                     # Database migrations
│   ├── env.py                   # Async-compatible Alembic environment
│   └── versions/
│       └── 0001_initial.py      # Full initial schema migration
├── pyproject.toml               # Project metadata + dependencies
└── ARCHITECTURE.md              # This document
```

## 3. Key Design Decisions

### 3.1 Double-Entry Accounting

**Decision**: Account balances are **never stored** in the `accounts` table.
All financial movement is recorded as `LedgerEntry` pairs and the balance
is derived on demand.

**Why**: Storing a denormalized balance creates two sources of truth that
can diverge under concurrent writes or process crashes. The ledger is the
single source of truth and is append-only (no UPDATE or DELETE operations).

**Trade-off**: Every balance read requires an aggregation query against
`ledger_entries`. This is mitigated by:
- PostgreSQL partial indexes on `debit_account_id` / `credit_account_id`.
- Future: materialized view or Redis cache refreshed after each entry.

**LedgerEntry invariant**: For every financial event, exactly one
`LedgerEntry` row is created where `amount_debited = amount_credited`
(debit_account_id source of funds, credit_account_id destination of funds).

```
Example: User deposits R$ 1,000

  LedgerEntry {
    debit_account_id:  platform_reserve_account  # funds left the bank
    credit_account_id: user_brl_account           # funds arrived at user
    amount:            1000.00
    currency:          BRL
    reference_type:    DEPOSIT
    reference_id:      <transaction_id>
  }
```

### 3.2 Concurrency Control (Optimistic vs Pessimistic)

**Strategy**: Row-level locking (pessimistic) for debit operations.

`AccountRepository.get_balance_for_update()` issues `SELECT FOR UPDATE`
on the `accounts` row before deriving and comparing the balance. The lock
is held until the encompassing transaction commits, preventing concurrent
requests from reading the same balance and both proceeding with a debit.

**When to use optimistic locking instead**:
- For operations where conflicts are rare and retry cost is low.
- Can be implemented with a `version` integer column on the model.
- The UPDATE only succeeds if `version` matches the value at read time.
- Suitable for profile updates, order status polling, etc.

**Trade-off**: `SELECT FOR UPDATE` serialises concurrent debits for the
same account. Under very high throughput, consider sharding accounts or
using a CRDT-based balance store for the hot path.

### 3.3 Idempotency

**Decision**: Orders carry a `idempotency_key` with a `UNIQUE` database constraint.

Two-layer enforcement:
1. **Service layer**: `TradingService.execute_trade()` looks up the key
   before creating any rows. On hit, the existing `Order` is returned.
2. **Database constraint**: If two concurrent requests both pass the
   service-layer check simultaneously, the second INSERT will raise
   `UniqueConstraintViolation`, which is caught and converted to
   `DuplicateIdempotencyKeyError`.

Exchange-level idempotency: `client_order_id = idempotency_key` is
passed to the exchange so that the exchange also deduplicates on retries.

**Trade-off**: Callers must generate a stable `idempotency_key` per
intended trade (not per retry). Using a client-generated UUID per
trade click is the recommended pattern.

### 3.4 Async Design

All I/O operations (DB queries, gateway calls) are `async/await` using:
- `asyncpg` as the PostgreSQL driver (native async, no thread overhead).
- `httpx.AsyncClient` for HTTP gateway calls.
- `AsyncSession` from SQLAlchemy 2.0 (`async_sessionmaker`).

The FastAPI dependency `get_db` yields a session per request and
commits on success or rolls back on exception, providing request-level
transaction atomicity as a baseline.

Service methods may create nested transactions (savepoints) for finer
control — e.g. marking an order FAILED without rolling back the
Transaction record that anchors the idempotency entry.

### 3.5 Integration Resilience

Gateways implement retry with exponential back-off using `tenacity`:
- Retries on: `ExternalGatewayTimeoutError`, `ExternalGatewayRateLimitError`.
- Max 3 attempts with back-off: 1s → 2s → 4s.
- Non-retryable errors (auth failure, invalid params) propagate immediately.

Gateway implementations follow the Abstract Base Class pattern so the
HTTP client can be swapped for a stub in tests and local development
without changing service code.

### 3.6 Failure Handling — Partial Fills

An order may be partially filled before the exchange or network fails.
The platform handles this as follows:

1. Each `FillEvent` is processed atomically (TradeExecution + LedgerEntry
   + Position update) inside the same DB transaction.
2. `TradeExecution.external_fill_id` is the exchange's fill ID, used
   for deduplication during re-processing.
3. If the process crashes after some fills are committed, the
   reconciliation job (TODO) calls `ExchangeGateway.get_order_status()`
   and replays unfilled fill events.

This ensures **at-least-once processing** of fills, with deduplication
preventing double-booking.

### 3.7 Outbox Pattern (TODO)

For `BankingService.deposit_funds`, the intended sequence is:
1. Persist `Transaction(PENDING)` in DB.
2. Call `BankingGateway.initiate_transfer()`.
3. Update `Transaction.reference_id` with the gateway's transfer ID.

If the process crashes between steps 1 and 2, the transfer is never
initiated and the Transaction is stuck as PENDING forever.

The **Outbox Pattern** solves this by:
1. Persisting both the `Transaction` AND a `outbox_message` row in the
   same DB transaction (atomic).
2. A separate background worker reads unprocessed outbox rows and
   makes the gateway call.
3. On success, the worker marks the outbox row as processed.

This guarantees at-least-once gateway calls even after process restarts.

## 4. Primary Flows

### 4.1 Deposit Flow

```
Client → POST /api/v1/accounts/bank-accounts/{id}/deposit
  │
  ├── BankingService.deposit_funds()
  │     ├── Validate bank account ownership
  │     ├── Validate platform account (currency)
  │     ├── Create Transaction (PENDING)          ← idempotency anchor
  │     ├── BankingGateway.initiate_transfer()    ← async, may fail
  │     └── Update Transaction (PROCESSING + gateway_ref)
  │
  └── [async] Webhook: POST /webhooks/banking/transfer-confirmed
        └── BankingService.confirm_deposit()
              ├── Guard: skip if already COMPLETED
              ├── Create LedgerEntry pair         ← double-entry
              │     debit:  platform_reserve_account
              │     credit: user_brl_account
              └── Update Transaction (COMPLETED)
```

### 4.2 Trade Flow

```
Client → POST /api/v1/orders
  │
  └── TradingService.execute_trade()
        ├── 1. Idempotency check (return early if key exists)
        ├── 2. Validate inputs (amount > 0, LIMIT needs price)
        ├── 3. Resolve quote-currency account
        ├── 4. SELECT FOR UPDATE on Account row
        │       derive balance from LedgerEntries
        │       raise InsufficientFundsError if needed
        ├── 5. Create Order (PENDING) + Transaction (TRADE)
        ├── 6. ExchangeGateway.submit_order()
        │       [on failure: Order → FAILED, rollback]
        └── 7. For each FillEvent:
                ├── Create TradeExecution
                ├── Create LedgerEntry pair       ← double-entry
                │     BUY:  debit fiat account, credit crypto account
                │     SELL: debit crypto account, credit fiat account
                ├── Upsert Position (weighted-average cost)
                └── Update Order.filled_amount + status
```

### 4.3 Portfolio Flow

```
Client → GET /api/v1/portfolio
  │
  └── PortfolioService.get_portfolio_summary()
        ├── Load positions from positions table
        ├── Resolve asset metadata (symbol, name)
        ├── Batch-fetch live prices from ExchangeGateway
        │     GET /prices?symbols=BTCBRL,ETHBRL,...
        ├── Derive cash balance from LedgerEntries
        │     SELECT SUM(credits) - SUM(debits) WHERE account_id=...
        └── Compute per-asset:
              market_value     = quantity × current_price
              unrealized_pnl   = market_value − (quantity × average_price)
              unrealized_pnl%  = unrealized_pnl / cost_basis × 100
```

## 5. Technology Choices

| Concern | Choice | Rationale |
|---|---|---|
| Web framework | FastAPI | Native async, automatic OpenAPI, Pydantic v2 integration |
| ORM | SQLAlchemy 2.0 | Mature, type-safe `mapped_column`, async support |
| DB driver | asyncpg | Fastest async PostgreSQL driver; no thread-pool overhead |
| Validation | Pydantic v2 | 5-10x faster than v1, strict mode, excellent type inference |
| Auth | python-jose + passlib | Industry-standard JWT + bcrypt |
| HTTP client | httpx | Async-native, test-friendly transport swapping |
| Retry | tenacity | Declarative, composable retry policies |
| Migrations | Alembic | Schema version control, autogenerate from models |
| Financial math | Python `Decimal` | Avoids IEEE 754 floating-point rounding errors |

## 6. Financial Integrity Rules

1. **Never** store balance directly. Derive from `ledger_entries`.
2. **Every** monetary event produces exactly **one** `LedgerEntry` pair.
3. `LedgerEntry.amount` is always **positive**. Direction = debit/credit accounts.
4. `LedgerEntry` rows are **append-only**. Reversals = new opposing entries.
5. **All** financial amounts use `Numeric(36, 18)` in the DB and `Decimal` in Python.
6. Debit and credit accounts in a `LedgerEntry` must **differ**.
7. The `amount` field must be **positive** (validated in `LedgerRepository`).

## 7. Pending Work (TODOs)

The following items are scaffolded with detailed `TODO` comments but not
fully implemented, as they require external system integration or
are out of scope for this architectural shell:

- `BankingService.confirm_deposit()` — full ledger posting (needs reserve account config).
- `BankingService.withdraw_funds()` — steps 4–7 (pattern mirrors deposit).
- `TradingService._process_fill()` — resolve actual crypto `Account` for asset leg.
- Reconciliation job — poll gateway for orders stuck in PARTIALLY_FILLED.
- Outbox Pattern — see `banking_service.py` class docstring.
- Domain event dispatch — events are defined in `app/events/` but not yet published.
- KYC checks before trading/withdrawals — hook point in `TradingService`.
- Deposit/withdrawal limits — per-day limits in `BankingService`.
- Asset repository — batch load assets by ID list in `PortfolioService`.
- Price caching — short-TTL Redis cache in `PortfolioService`.
- Refresh token endpoint — `/auth/refresh`.
- Webhook handler — `/webhooks/banking/transfer-confirmed`.

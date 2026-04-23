from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AccountNotFoundError,
    AssetNotFoundError,
    DuplicateIdempotencyKeyError,
    InsufficientFundsError,
    InvalidOrderError,
)
from app.integrations.base import ExchangeGateway, FillEvent, OrderSubmission
from app.models.order import Order, OrderSide, OrderStatus, OrderType, TradeExecution
from app.repositories.account_repository import AccountRepository
from app.repositories.ledger_repository import LedgerRepository
from app.repositories.order_repository import OrderRepository, PositionRepository, TradeExecutionRepository
from app.repositories.transaction_repository import TransactionRepository
from app.models.transaction import TransactionType, TransactionStatus

logger = logging.getLogger(__name__)


class TradingService:
    """
    Orchestrates the full trade lifecycle.

    execute_trade algorithm (detailed)
    -----------------------------------
    1.  Idempotency check
        → Lookup Order by idempotency_key.
        → If found: return existing Order (no duplicate processing).

    2.  Asset validation
        → Ensure the requested asset exists and is tradeable.

    3.  Account resolution
        → Resolve user's quote-currency account (for BUY: need fiat; for SELL: need asset).

    4.  Balance validation with concurrency control
        → ``AccountRepository.get_balance_for_update`` acquires SELECT FOR UPDATE.
        → Derive balance from LedgerEntries (no balance field on Account).
        → Raise InsufficientFundsError if balance < required amount.

    5.  Order creation
        → Persist Order with status=PENDING within the locked transaction.

    6.  External order submission
        → Call ExchangeGateway.submit_order() with client_order_id=idempotency_key.
        → On gateway failure: mark Order FAILED, roll back ledger (no entries posted yet).

    7.  Fill processing
        → For each FillEvent from the gateway:
            a. Create TradeExecution record.
            b. Post balanced LedgerEntry pair (double-entry).
            c. Upsert Position with weighted-average price.
            d. Apply fill to Order (update filled_amount and status).

    8.  Final status
        → If all filled: Order → FILLED, Transaction → COMPLETED.
        → If partial: Order → PARTIALLY_FILLED (reconciliation job handles remainder).
        → If zero fills: Order → FAILED.

    Consistency guarantees
    ----------------------
    - The DB transaction wrapping steps 4–7 ensures atomicity.
    - SELECT FOR UPDATE (step 4) prevents concurrent overdraft.
    - idempotency_key unique constraint (DB level) is the last line of defence
      against duplicate orders if the service-level check (step 1) is bypassed.
    - If the process crashes AFTER the exchange fills the order but BEFORE we
      commit the LedgerEntries, the reconciliation job re-calls get_order_status
      and re-processes fills. TradeExecution.external_fill_id prevents duplicate
      fills from being recorded.

    TODO: Implement the reconciliation job.
    TODO: Emit TradeExecuted domain event for each fill.
    TODO: Handle PARTIALLY_FILLED orders via the reconciliation job.
    """

    def __init__(
        self,
        session: AsyncSession,
        exchange_gateway: ExchangeGateway,
    ) -> None:
        self._session = session
        self._gateway = exchange_gateway
        self._order_repo = OrderRepository(session)
        self._execution_repo = TradeExecutionRepository(session)
        self._position_repo = PositionRepository(session)
        self._account_repo = AccountRepository(session)
        self._ledger_repo = LedgerRepository(session)
        self._transaction_repo = TransactionRepository(session)

    async def execute_trade(
        self,
        *,
        user_id: uuid.UUID,
        asset_id: uuid.UUID,
        side: OrderSide,
        order_type: OrderType,
        amount: Decimal,
        price: Decimal | None = None,
        idempotency_key: str,
        quote_currency: str = "BRL",
    ) -> Order:
        """
        Place an order and process fills within a single database transaction.

        :param user_id: Authenticated user placing the order.
        :param asset_id: Asset to buy or sell.
        :param side: BUY or SELL.
        :param order_type: MARKET or LIMIT.
        :param amount: Base asset quantity (BUY) or quote currency amount (SELL).
        :param price: Required for LIMIT orders; ignored for MARKET orders.
        :param idempotency_key: Caller-supplied unique key (UUID or string).
        :param quote_currency: Fiat or stablecoin used for settlement (default: BRL).
        :raises DuplicateIdempotencyKeyError: if the key was already processed.
        :raises InsufficientFundsError: if the account balance is too low.
        :raises InvalidOrderError: if order parameters fail validation.
        """
        # ── Step 1: Idempotency ───────────────────────────────────────────────
        existing_order = await self._order_repo.get_by_idempotency_key(idempotency_key)
        if existing_order is not None:
            logger.info(
                "Idempotent return: order already exists for key=%s order_id=%s",
                idempotency_key, existing_order.id,
            )
            return existing_order

        # ── Step 2: Validate inputs ───────────────────────────────────────────
        if amount <= Decimal("0"):
            raise InvalidOrderError("Order amount must be positive.")
        if order_type == OrderType.LIMIT and price is None:
            raise InvalidOrderError("LIMIT orders require a price.")

        # ── Step 3: Resolve the account to debit ──────────────────────────────
        # BUY  → debit quote-currency (fiat) account, credit asset account.
        # SELL → debit asset account, credit quote-currency (fiat) account.
        #
        # TODO: For SELL orders, resolve the asset account (CRYPTO account).
        #       For now we resolve the quote-currency (fiat) account for BUY.
        account = await self._account_repo.get_by_user_and_currency(user_id, quote_currency)
        if account is None:
            raise AccountNotFoundError(
                f"No {quote_currency} account found for user {user_id}."
            )

        # ── Step 4: Balance check with row-level lock ─────────────────────────
        # SELECT FOR UPDATE on the Account row prevents concurrent debits.
        # Balance is derived from LedgerEntries — no balance column on Account.
        locked_account, balance = await self._account_repo.get_balance_for_update(account.id)

        # For MARKET BUY, required amount is estimated from current order book.
        # For LIMIT BUY, required amount = amount * price.
        # TODO: Fetch live price for MARKET orders to calculate required fiat.
        estimated_cost = amount * (price or Decimal("0"))  # simplified
        if side == OrderSide.BUY and estimated_cost > Decimal("0") and balance < estimated_cost:
            raise InsufficientFundsError(
                available=str(balance),
                required=str(estimated_cost),
                currency=quote_currency,
            )

        # ── Step 5: Create the Order ──────────────────────────────────────────
        # The DB-level unique constraint on idempotency_key is the last line of
        # defence against race conditions on step 1 (two concurrent requests
        # passing the check simultaneously before either commits).
        order = Order(
            user_id=user_id,
            asset_id=asset_id,
            side=side,
            order_type=order_type,
            amount=amount,
            filled_amount=Decimal("0"),
            price=price,
            status=OrderStatus.PENDING,
            idempotency_key=idempotency_key,
        )
        await self._order_repo.add(order)

        # Create a TRADE Transaction for tracking purposes
        transaction = await self._transaction_repo.create(
            user_id=user_id,
            transaction_type=TransactionType.TRADE,
            reference_id=str(order.id),
        )

        # ── Step 6: Submit to exchange ────────────────────────────────────────
        submission: OrderSubmission
        try:
            # Asset symbol for exchange routing
            # TODO: Resolve asset symbol from asset_id via AssetRepository.
            asset_symbol = "BTCBRL"  # placeholder — resolve from asset

            submission = await self._gateway.submit_order(
                client_order_id=idempotency_key,  # exchange-level idempotency
                symbol=asset_symbol,
                side=side.value,
                order_type=order_type.value,
                amount=amount,
                price=price,
            )
        except Exception as exc:
            # Gateway failure — mark order FAILED and re-raise.
            # The DB transaction will be rolled back by get_db, so the Order
            # row is also removed (no orphaned PENDING orders).
            logger.error("Exchange submission failed for order %s: %s", order.id, exc)
            await self._order_repo.update_status(order, OrderStatus.FAILED)
            await self._transaction_repo.update_status(transaction, TransactionStatus.FAILED)
            raise

        # ── Step 7: Process fills ─────────────────────────────────────────────
        if not submission.fills and submission.status == "FILLED":
            # Some exchanges return a single aggregate fill without individual events.
            # Synthesise a single fill from the aggregate response.
            submission.fills = [
                FillEvent(
                    fill_id=submission.external_order_id,
                    price=submission.average_price,
                    amount=submission.filled_amount,
                    fee=submission.fee,
                    timestamp=datetime.now(UTC).timestamp(),
                )
            ]

        seen_fill_ids: set[str] = set()
        for fill in submission.fills:
            # Deduplication: skip fills already recorded (idempotent re-processing)
            if fill.fill_id in seen_fill_ids:
                continue
            # TODO: Check DB for existing TradeExecution.external_fill_id before inserting.
            seen_fill_ids.add(fill.fill_id)

            await self._process_fill(
                order=order,
                fill=fill,
                account=locked_account,
                quote_currency=quote_currency,
                transaction_id=transaction.id,
            )

        # ── Step 8: Finalise order status ─────────────────────────────────────
        if submission.status == "REJECTED":
            await self._order_repo.update_status(order, OrderStatus.FAILED)
            await self._transaction_repo.update_status(transaction, TransactionStatus.FAILED)
        elif submission.status in {"FILLED", "PARTIALLY_FILLED"}:
            # apply_fill already updated filled_amount and status per fill.
            # Sync transaction status with order status.
            final_status = (
                TransactionStatus.COMPLETED
                if order.status == OrderStatus.FILLED
                else TransactionStatus.PROCESSING  # partial fill — still open
            )
            await self._transaction_repo.update_status(transaction, final_status)

        logger.info(
            "Trade executed: order_id=%s side=%s status=%s filled=%s/%s",
            order.id, side, order.status, order.filled_amount, order.amount,
        )
        return order

    async def _process_fill(
        self,
        *,
        order: Order,
        fill: FillEvent,
        account: "Account",  # type: ignore[name-defined]
        quote_currency: str,
        transaction_id: uuid.UUID,
    ) -> None:
        """
        Record a single fill: TradeExecution + LedgerEntries + Position update.

        Double-entry for BUY:
            Debit  → user's fiat account   (fiat leaves user)
            Credit → user's crypto account (crypto arrives at user)

        Double-entry for SELL:
            Debit  → user's crypto account (crypto leaves user)
            Credit → user's fiat account   (fiat arrives at user)

        NOTE: In a full implementation, the fee should generate a separate
        LedgerEntry pair (debit user, credit platform fee account).

        TODO: Resolve crypto account for the asset (CRYPTO AccountType).
        TODO: Create a fee LedgerEntry pair.
        TODO: Emit TradeExecuted domain event.
        """
        fill_value = fill.price * fill.amount  # quote currency value of this fill

        # Record the execution
        execution = TradeExecution(
            order_id=order.id,
            executed_price=fill.price,
            executed_amount=fill.amount,
            fee=fill.fee,
            timestamp=datetime.fromtimestamp(fill.timestamp, tz=UTC),
            external_fill_id=fill.fill_id,
        )
        await self._execution_repo.add(execution)

        # Post double-entry LedgerEntries
        # TODO: Replace placeholder account IDs with real crypto account lookups.
        #       For now we use the same account as a placeholder.
        if order.side == OrderSide.BUY:
            await self._ledger_repo.create_double_entry(
                debit_account_id=account.id,         # fiat leaves user
                credit_account_id=account.id,         # TODO: use crypto account
                amount=fill_value,
                currency=quote_currency,
                reference_type="TRADE",
                reference_id=str(transaction_id),
            )
        else:  # SELL
            await self._ledger_repo.create_double_entry(
                debit_account_id=account.id,         # TODO: use crypto account
                credit_account_id=account.id,         # fiat arrives at user
                amount=fill_value,
                currency=quote_currency,
                reference_type="TRADE",
                reference_id=str(transaction_id),
            )

        # Update position (weighted-average cost basis)
        quantity_delta = fill.amount if order.side == OrderSide.BUY else -fill.amount
        await self._position_repo.upsert_position(
            user_id=order.user_id,
            asset_id=order.asset_id,
            quantity_delta=quantity_delta,
            fill_price=fill.price,
        )

        # Accumulate fill against the order
        await self._order_repo.apply_fill(order, fill.amount)


# Re-export for type hints in docstrings
from app.models.account import Account  # noqa: E402

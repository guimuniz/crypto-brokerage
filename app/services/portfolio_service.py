from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.base import ExchangeGateway, InstrumentPrice
from app.models.asset import Asset
from app.repositories.account_repository import AccountRepository
from app.repositories.order_repository import PositionRepository

logger = logging.getLogger(__name__)


@dataclass
class PositionSummary:
    """Per-asset holding enriched with live market data."""

    asset_id: uuid.UUID
    asset_symbol: str
    asset_name: str
    quantity: Decimal
    average_price: Decimal        # cost basis (weighted average)
    current_price: Decimal        # live market price (ask)
    market_value: Decimal         # quantity * current_price
    unrealized_pnl: Decimal       # market_value - (quantity * average_price)
    unrealized_pnl_pct: Decimal   # unrealized_pnl / (quantity * average_price) * 100


@dataclass
class PortfolioSummary:
    """Aggregated portfolio snapshot for the authenticated user."""

    user_id: uuid.UUID
    positions: list[PositionSummary] = field(default_factory=list)
    total_market_value: Decimal = Decimal("0")
    total_cost_basis: Decimal = Decimal("0")
    total_unrealized_pnl: Decimal = Decimal("0")
    total_unrealized_pnl_pct: Decimal = Decimal("0")
    # Cash balance across all fiat accounts
    cash_balance: Decimal = Decimal("0")
    cash_currency: str = "BRL"


class PortfolioService:
    """
    Aggregates a user's positions and computes PnL metrics.

    Design notes
    ------------
    - Positions are read from the ``positions`` table (explicitly maintained).
      An alternative (purer) approach is to derive them from LedgerEntries,
      but that requires a full ledger scan per asset — impractical at scale.
    - Live prices are fetched from the ExchangeGateway in a single batched call
      to minimise latency and gateway round-trips.
    - Realized PnL is tracked per TradeExecution but not yet aggregated here.
      See TODO below.

    TODO: Add realized PnL calculation from TradeExecution records.
    TODO: Add historical portfolio value snapshots (time-series).
    TODO: Cache live prices with a short TTL (e.g. Redis, 5s) to reduce
          gateway calls under high read load.
    TODO: Support multi-currency portfolios (aggregate to a single base currency
          using FX rates from the ExchangeGateway).
    """

    def __init__(
        self,
        session: AsyncSession,
        exchange_gateway: ExchangeGateway,
    ) -> None:
        self._session = session
        self._gateway = exchange_gateway
        self._position_repo = PositionRepository(session)
        self._account_repo = AccountRepository(session)

    async def get_portfolio_summary(
        self,
        user_id: uuid.UUID,
        *,
        quote_currency: str = "BRL",
    ) -> PortfolioSummary:
        """
        Build a full portfolio snapshot for *user_id*.

        Steps:
        1. Load all positions from the positions table.
        2. Resolve asset metadata (symbol, name) from each position.
        3. Batch-fetch live prices for all held assets from the exchange.
        4. Compute unrealized PnL per position.
        5. Compute cash balance from LedgerEntries.
        6. Aggregate totals.

        :param user_id: The user whose portfolio to summarize.
        :param quote_currency: Currency to denominate PnL and market values.
        :returns: PortfolioSummary with per-asset breakdowns and aggregates.
        """
        # Step 1: Load positions
        positions = await self._position_repo.get_by_user(user_id)
        if not positions:
            return PortfolioSummary(user_id=user_id, cash_currency=quote_currency)

        # Step 2: Resolve asset metadata
        # TODO: Use AssetRepository to batch-load by asset_id list.
        asset_map: dict[uuid.UUID, Asset] = {}
        for position in positions:
            # Lazy load for now — replace with batched IN query.
            asset = await self._session.get(Asset, position.asset_id)
            if asset is not None:
                asset_map[position.asset_id] = asset

        # Step 3: Batch-fetch live prices
        # Build exchange symbols: e.g. "BTCBRL", "ETHBRL"
        symbols = [
            f"{asset_map[p.asset_id].symbol}{quote_currency}"
            for p in positions
            if p.asset_id in asset_map
        ]
        prices: dict[str, InstrumentPrice] = {}
        if symbols:
            try:
                prices = await self._gateway.get_instrument_prices(symbols)
            except Exception as exc:
                # Degrade gracefully — return positions without live prices.
                logger.warning("Failed to fetch live prices: %s", exc)

        # Step 4: Build position summaries
        position_summaries: list[PositionSummary] = []
        total_market_value = Decimal("0")
        total_cost_basis = Decimal("0")

        for position in positions:
            asset = asset_map.get(position.asset_id)
            if asset is None:
                continue

            symbol_key = f"{asset.symbol}{quote_currency}"
            price_data = prices.get(symbol_key)
            current_price = price_data.last if price_data else Decimal("0")

            market_value = position.quantity * current_price
            cost_basis = position.quantity * position.average_price
            unrealized_pnl = market_value - cost_basis
            unrealized_pnl_pct = (
                (unrealized_pnl / cost_basis * Decimal("100"))
                if cost_basis > Decimal("0")
                else Decimal("0")
            )

            position_summaries.append(
                PositionSummary(
                    asset_id=position.asset_id,
                    asset_symbol=asset.symbol,
                    asset_name=asset.name,
                    quantity=position.quantity,
                    average_price=position.average_price,
                    current_price=current_price,
                    market_value=market_value,
                    unrealized_pnl=unrealized_pnl,
                    unrealized_pnl_pct=unrealized_pnl_pct,
                )
            )
            total_market_value += market_value
            total_cost_basis += cost_basis

        # Step 5: Compute cash balance from LedgerEntries
        cash_account = await self._account_repo.get_by_user_and_currency(
            user_id, quote_currency
        )
        cash_balance = Decimal("0")
        if cash_account is not None:
            cash_balance = await self._account_repo.get_balance(cash_account.id)

        # Step 6: Aggregate
        total_unrealized_pnl = total_market_value - total_cost_basis
        total_unrealized_pnl_pct = (
            (total_unrealized_pnl / total_cost_basis * Decimal("100"))
            if total_cost_basis > Decimal("0")
            else Decimal("0")
        )

        return PortfolioSummary(
            user_id=user_id,
            positions=position_summaries,
            total_market_value=total_market_value,
            total_cost_basis=total_cost_basis,
            total_unrealized_pnl=total_unrealized_pnl,
            total_unrealized_pnl_pct=total_unrealized_pnl_pct,
            cash_balance=cash_balance,
            cash_currency=quote_currency,
        )

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession, ExchangeGatewayDep
from app.api.schemas.portfolio import PortfolioSummaryRead, PositionRead
from app.services.portfolio_service import PortfolioService

router = APIRouter(prefix="/portfolio", tags=["Portfolio"])


@router.get(
    "",
    response_model=PortfolioSummaryRead,
    summary="Get portfolio summary with live PnL",
    description=(
        "Returns all positions with current market prices, unrealized PnL, "
        "and cash balances. Prices are fetched live from the exchange gateway."
    ),
)
async def get_portfolio(
    current_user: CurrentUser,
    db: DbSession,
    exchange_gateway: ExchangeGatewayDep,
    quote_currency: str = "BRL",
) -> PortfolioSummaryRead:
    """
    Return the authenticated user's portfolio summary.

    - Positions: loaded from the positions table (weighted-average cost basis).
    - Live prices: fetched in a single batch call to the exchange gateway.
    - Unrealized PnL: (current_price - average_price) * quantity per asset.
    - Cash balance: derived from LedgerEntries for the user's fiat account.
    """
    service = PortfolioService(session=db, exchange_gateway=exchange_gateway)
    summary = await service.get_portfolio_summary(
        current_user.id, quote_currency=quote_currency
    )

    return PortfolioSummaryRead(
        user_id=summary.user_id,
        positions=[
            PositionRead(
                asset_id=p.asset_id,
                asset_symbol=p.asset_symbol,
                asset_name=p.asset_name,
                quantity=p.quantity,
                average_price=p.average_price,
                current_price=p.current_price,
                market_value=p.market_value,
                unrealized_pnl=p.unrealized_pnl,
                unrealized_pnl_pct=p.unrealized_pnl_pct,
            )
            for p in summary.positions
        ],
        total_market_value=summary.total_market_value,
        total_cost_basis=summary.total_cost_basis,
        total_unrealized_pnl=summary.total_unrealized_pnl,
        total_unrealized_pnl_pct=summary.total_unrealized_pnl_pct,
        cash_balance=summary.cash_balance,
        cash_currency=summary.cash_currency,
    )

from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel


class PositionRead(BaseModel):
    asset_id: uuid.UUID
    asset_symbol: str
    asset_name: str
    quantity: Decimal
    average_price: Decimal
    current_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: Decimal


class PortfolioSummaryRead(BaseModel):
    user_id: uuid.UUID
    positions: list[PositionRead]
    total_market_value: Decimal
    total_cost_basis: Decimal
    total_unrealized_pnl: Decimal
    total_unrealized_pnl_pct: Decimal
    cash_balance: Decimal
    cash_currency: str

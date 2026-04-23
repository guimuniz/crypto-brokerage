from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.models.order import OrderSide, OrderStatus, OrderType


class OrderCreate(BaseModel):
    asset_id: uuid.UUID
    side: OrderSide
    order_type: OrderType
    amount: Decimal = Field(gt=Decimal("0"), description="Quantity of the base asset")
    price: Decimal | None = Field(default=None, gt=Decimal("0"), description="Required for LIMIT orders")
    idempotency_key: str = Field(
        min_length=1, max_length=128,
        description="Unique caller-supplied key to prevent duplicate orders"
    )
    quote_currency: str = Field(default="BRL", min_length=2, max_length=10)

    @model_validator(mode="after")
    def validate_limit_price(self) -> "OrderCreate":
        if self.order_type == OrderType.LIMIT and self.price is None:
            raise ValueError("LIMIT orders require a price.")
        if self.order_type == OrderType.MARKET and self.price is not None:
            raise ValueError("MARKET orders must not have a price.")
        return self


class TradeExecutionRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    order_id: uuid.UUID
    executed_price: Decimal
    executed_amount: Decimal
    fee: Decimal
    timestamp: datetime
    external_fill_id: str | None


class OrderRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    user_id: uuid.UUID
    asset_id: uuid.UUID
    side: OrderSide
    order_type: OrderType
    amount: Decimal
    filled_amount: Decimal
    price: Decimal | None
    status: OrderStatus
    idempotency_key: str
    created_at: datetime
    executions: list[TradeExecutionRead] = Field(default_factory=list)

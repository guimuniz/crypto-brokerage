from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order, OrderStatus, Position, TradeExecution
from app.repositories.base import BaseRepository


class OrderRepository(BaseRepository[Order]):
    model = Order

    async def get_by_idempotency_key(self, idempotency_key: str) -> Order | None:
        """
        Look up an existing order by the caller-supplied idempotency key.

        This is the first check in execute_trade. If an order is found, the
        service returns it directly without creating a duplicate, ensuring
        exactly-once semantics across network retries.
        """
        result = await self._session.execute(
            select(Order).where(Order.idempotency_key == idempotency_key)
        )
        return result.scalars().first()

    async def get_by_user(
        self,
        user_id: uuid.UUID,
        *,
        status: OrderStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Order]:
        query = select(Order).where(Order.user_id == user_id)
        if status is not None:
            query = query.where(Order.status == status)
        query = query.order_by(Order.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def update_status(self, order: Order, status: OrderStatus) -> Order:
        return await self.update(order, status=status)

    async def apply_fill(
        self, order: Order, filled_qty: Decimal
    ) -> Order:
        """
        Accumulate a fill against the order's total amount.

        Transitions:
        - filled_amount < amount  →  PARTIALLY_FILLED
        - filled_amount == amount →  FILLED
        """
        new_filled = order.filled_amount + filled_qty
        new_status = (
            OrderStatus.FILLED if new_filled >= order.amount else OrderStatus.PARTIALLY_FILLED
        )
        return await self.update(order, filled_amount=new_filled, status=new_status)


class TradeExecutionRepository(BaseRepository[TradeExecution]):
    model = TradeExecution

    async def get_by_order(self, order_id: uuid.UUID) -> list[TradeExecution]:
        result = await self._session.execute(
            select(TradeExecution)
            .where(TradeExecution.order_id == order_id)
            .order_by(TradeExecution.timestamp)
        )
        return list(result.scalars().all())


class PositionRepository(BaseRepository[Position]):
    model = Position

    async def get_by_user_and_asset(
        self, user_id: uuid.UUID, asset_id: uuid.UUID
    ) -> Position | None:
        result = await self._session.execute(
            select(Position).where(
                Position.user_id == user_id,
                Position.asset_id == asset_id,
            )
        )
        return result.scalars().first()

    async def get_by_user(self, user_id: uuid.UUID) -> list[Position]:
        result = await self._session.execute(
            select(Position).where(Position.user_id == user_id)
        )
        return list(result.scalars().all())

    async def upsert_position(
        self,
        user_id: uuid.UUID,
        asset_id: uuid.UUID,
        quantity_delta: Decimal,
        fill_price: Decimal,
    ) -> Position:
        """
        Update or create a position using the weighted-average cost method.

        Weighted-average cost formula (BUY):
            new_avg = (old_qty * old_avg + fill_qty * fill_price) / (old_qty + fill_qty)

        For SELL orders, ``quantity_delta`` is negative. Average price is NOT
        recalculated on sells — only on buys (cost-basis is preserved).
        """
        position = await self.get_by_user_and_asset(user_id, asset_id)

        if position is None:
            position = Position(
                user_id=user_id,
                asset_id=asset_id,
                quantity=quantity_delta,
                average_price=fill_price if quantity_delta > 0 else Decimal("0"),
            )
            return await self.add(position)

        old_qty = position.quantity
        old_avg = position.average_price
        new_qty = old_qty + quantity_delta

        if quantity_delta > 0:
            # BUY: recalculate weighted average
            new_avg = (old_qty * old_avg + quantity_delta * fill_price) / new_qty
        else:
            # SELL: keep cost basis unchanged
            new_avg = old_avg

        return await self.update(position, quantity=new_qty, average_price=new_avg)

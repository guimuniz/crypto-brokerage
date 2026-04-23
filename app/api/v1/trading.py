from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession, ExchangeGatewayDep
from app.api.schemas.order import OrderCreate, OrderRead
from app.core.exceptions import (
    AccountNotFoundError,
    DuplicateIdempotencyKeyError,
    InsufficientFundsError,
    InvalidOrderError,
)
from app.repositories.order_repository import OrderRepository
from app.services.trading_service import TradingService

router = APIRouter(prefix="/orders", tags=["Trading"])


@router.post(
    "",
    response_model=OrderRead,
    status_code=status.HTTP_201_CREATED,
    summary="Place an order (BUY or SELL)",
    description=(
        "Idempotent: if an order with the same ``idempotency_key`` already exists, "
        "it is returned without creating a duplicate. "
        "The caller must supply a unique ``idempotency_key`` per intended order."
    ),
)
async def create_order(
    payload: OrderCreate,
    current_user: CurrentUser,
    db: DbSession,
    exchange_gateway: ExchangeGatewayDep,
) -> OrderRead:
    """
    Execute a trade order.

    Flow:
    1. Validate idempotency key (return existing order if found).
    2. Check user's balance via ledger.
    3. Lock the account row (SELECT FOR UPDATE).
    4. Submit to the exchange.
    5. Record fills as TradeExecution + LedgerEntries.
    6. Return the final Order state.
    """
    service = TradingService(session=db, exchange_gateway=exchange_gateway)
    try:
        order = await service.execute_trade(
            user_id=current_user.id,
            asset_id=payload.asset_id,
            side=payload.side,
            order_type=payload.order_type,
            amount=payload.amount,
            price=payload.price,
            idempotency_key=payload.idempotency_key,
            quote_currency=payload.quote_currency,
        )
        return OrderRead.model_validate(order)
    except DuplicateIdempotencyKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=exc.message,
        ) from exc
    except InsufficientFundsError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.message,
        ) from exc
    except (AccountNotFoundError, InvalidOrderError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.message,
        ) from exc


@router.get(
    "/{order_id}",
    response_model=OrderRead,
    summary="Get order details",
)
async def get_order(
    order_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> OrderRead:
    repo = OrderRepository(db)
    order = await repo.get_by_id(order_id)

    if order is None or order.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order {order_id} not found.",
        )

    return OrderRead.model_validate(order)


@router.get(
    "",
    response_model=list[OrderRead],
    summary="List orders for the authenticated user",
)
async def list_orders(
    current_user: CurrentUser,
    db: DbSession,
    limit: int = 50,
    offset: int = 0,
) -> list[OrderRead]:
    repo = OrderRepository(db)
    orders = await repo.get_by_user(current_user.id, limit=limit, offset=offset)
    return [OrderRead.model_validate(o) for o in orders]

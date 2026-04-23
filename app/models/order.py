from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.asset import Asset
    from app.models.user import User

# ── Enums ─────────────────────────────────────────────────────────────────────

# Numeric precision for monetary values.
# 36 total digits, 18 decimal places — safely covers crypto (18 decimals for ETH)
# and very large fiat amounts without floating-point loss.
AMOUNT_PRECISION = 36
AMOUNT_SCALE = 18


class OrderSide(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, enum.Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderStatus(str, enum.Enum):
    """
    Order lifecycle state machine:

        PENDING → PARTIALLY_FILLED → FILLED (terminal)
               ↘                  ↘ FAILED  (terminal)
                → FAILED           → CANCELLED (terminal)
               → CANCELLED
    """

    PENDING = "PENDING"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    @property
    def is_terminal(self) -> bool:
        return self in {OrderStatus.FILLED, OrderStatus.FAILED, OrderStatus.CANCELLED}


# ── Models ────────────────────────────────────────────────────────────────────


class Order(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Represents a client instruction to buy or sell an asset.

    Idempotency
    -----------
    ``idempotency_key`` must be provided by the caller and is enforced unique
    at the database level. Before inserting, the service layer checks for an
    existing order with the same key and returns it directly, preventing double
    submissions in case of network retries.

    Partial fills
    -------------
    ``filled_amount`` tracks how much has been executed so far.
    When ``filled_amount == amount`` the status transitions to FILLED.
    When 0 < filled_amount < amount the status is PARTIALLY_FILLED.
    TradeExecution records each individual fill.
    """

    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_orders_idempotency_key"),
        Index("ix_orders_user_id_status", "user_id", "status"),
        Index("ix_orders_asset_id", "asset_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    side: Mapped[OrderSide] = mapped_column(
        Enum(OrderSide, name="order_side_enum"), nullable=False
    )
    order_type: Mapped[OrderType] = mapped_column(
        Enum(OrderType, name="order_type_enum"), nullable=False
    )
    # Total requested quantity (asset units for BUY; quote currency for SELL).
    amount: Mapped[Decimal] = mapped_column(
        Numeric(AMOUNT_PRECISION, AMOUNT_SCALE), nullable=False
    )
    # Cumulative filled quantity — updated by each TradeExecution.
    filled_amount: Mapped[Decimal] = mapped_column(
        Numeric(AMOUNT_PRECISION, AMOUNT_SCALE), nullable=False, default=Decimal("0")
    )
    # Limit price (NULL for MARKET orders).
    price: Mapped[Decimal | None] = mapped_column(
        Numeric(AMOUNT_PRECISION, AMOUNT_SCALE), nullable=True
    )
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status_enum"),
        nullable=False,
        default=OrderStatus.PENDING,
        index=True,
    )
    # Caller-supplied unique key — prevents duplicate orders on retry.
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped[User] = relationship("User", back_populates="orders")
    asset: Mapped[Asset] = relationship("Asset", back_populates="orders")
    executions: Mapped[list[TradeExecution]] = relationship(
        "TradeExecution",
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"<Order id={self.id} side={self.side} type={self.order_type}"
            f" status={self.status} filled={self.filled_amount}/{self.amount}>"
        )


class TradeExecution(UUIDPrimaryKeyMixin, Base):
    """
    Records a single fill event for an Order.

    An order may have multiple TradeExecution records (partial fills).
    Each execution triggers:
    1. An update to ``Order.filled_amount`` (and status).
    2. Creation of a balanced pair of LedgerEntries.

    ``timestamp`` is the time the fill was confirmed by the exchange,
    not the time this record was inserted.
    """

    __tablename__ = "trade_executions"
    __table_args__ = (Index("ix_trade_executions_order_id", "order_id"),)

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Price at which this fill was executed (in quote currency).
    executed_price: Mapped[Decimal] = mapped_column(
        Numeric(AMOUNT_PRECISION, AMOUNT_SCALE), nullable=False
    )
    # Quantity of the base asset that was filled in this execution.
    executed_amount: Mapped[Decimal] = mapped_column(
        Numeric(AMOUNT_PRECISION, AMOUNT_SCALE), nullable=False
    )
    # Exchange-side fill fee (quote currency). Tracked for PnL calculations.
    fee: Mapped[Decimal] = mapped_column(
        Numeric(AMOUNT_PRECISION, AMOUNT_SCALE), nullable=False, default=Decimal("0")
    )
    # Timestamp from the exchange's fill confirmation message.
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # External fill ID from the exchange (for reconciliation).
    external_fill_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    order: Mapped[Order] = relationship("Order", back_populates="executions")

    def __repr__(self) -> str:
        return (
            f"<TradeExecution id={self.id} order_id={self.order_id}"
            f" price={self.executed_price} amount={self.executed_amount}>"
        )


class Position(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Aggregated holding of an asset for a given user.

    ⚠️  Design note
    ---------------
    Positions CAN be derived entirely from LedgerEntries (preferred in a pure
    double-entry system). However, storing them explicitly avoids expensive
    full-ledger scans for portfolio reads and simplifies average-price tracking.

    Trade-off: the Position must be updated atomically with the LedgerEntries
    in the same database transaction. See PortfolioService and TradingService.

    ``average_price`` uses the weighted-average cost method:
        new_avg = (old_qty * old_avg + fill_qty * fill_price) / (old_qty + fill_qty)
    """

    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint("user_id", "asset_id", name="uq_positions_user_asset"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Net quantity held (positive = long). Short positions use negative values.
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(AMOUNT_PRECISION, AMOUNT_SCALE), nullable=False, default=Decimal("0")
    )
    # Weighted-average cost per unit in the account's quote currency.
    average_price: Mapped[Decimal] = mapped_column(
        Numeric(AMOUNT_PRECISION, AMOUNT_SCALE), nullable=False, default=Decimal("0")
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped[User] = relationship("User", back_populates="positions")
    asset: Mapped[Asset] = relationship("Asset", back_populates="positions")

    def __repr__(self) -> str:
        return (
            f"<Position user_id={self.user_id} asset_id={self.asset_id}"
            f" qty={self.quantity} avg={self.average_price}>"
        )

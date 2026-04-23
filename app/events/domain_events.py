from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from app.events.base import DomainEvent


# ── User Events ───────────────────────────────────────────────────────────────


@dataclass(frozen=True, kw_only=True)
class UserRegistered(DomainEvent):
    """
    Emitted after a new user is successfully created.

    Consumers:
    - KYC service: initiate identity verification workflow.
    - Email service: send welcome email.
    - Analytics: track user acquisition funnel.
    """

    user_id: uuid.UUID
    email: str
    country: str
    account_id: uuid.UUID  # the default account created at registration


@dataclass(frozen=True, kw_only=True)
class KYCStatusChanged(DomainEvent):
    """
    Emitted when a user's KYC status transitions.

    Consumers:
    - Notification service: inform user of approval/rejection.
    - Risk service: update risk profile.
    """

    user_id: uuid.UUID
    old_status: str
    new_status: str


# ── Banking Events ────────────────────────────────────────────────────────────


@dataclass(frozen=True, kw_only=True)
class FundsDeposited(DomainEvent):
    """
    Emitted after a deposit is confirmed and LedgerEntries are posted.

    Consumers:
    - Notification service: alert user of successful deposit.
    - Analytics: track deposit volume.
    - Risk service: evaluate deposit patterns.
    """

    user_id: uuid.UUID
    account_id: uuid.UUID
    transaction_id: uuid.UUID
    amount: Decimal
    currency: str
    external_transfer_id: str


@dataclass(frozen=True, kw_only=True)
class FundsWithdrawn(DomainEvent):
    """
    Emitted after a withdrawal is initiated and funds are debited.

    Consumers:
    - Notification service: confirm withdrawal to user.
    - Compliance: log outbound fund movement for AML reporting.
    """

    user_id: uuid.UUID
    account_id: uuid.UUID
    transaction_id: uuid.UUID
    amount: Decimal
    currency: str
    external_transfer_id: str
    bank_account_id: uuid.UUID


# ── Trading Events ────────────────────────────────────────────────────────────


@dataclass(frozen=True, kw_only=True)
class OrderPlaced(DomainEvent):
    """
    Emitted immediately after an Order is created and sent to the exchange.

    Consumers:
    - Analytics: real-time order flow tracking.
    - Risk service: detect unusual trading patterns.
    """

    order_id: uuid.UUID
    user_id: uuid.UUID
    asset_id: uuid.UUID
    side: str
    order_type: str
    amount: Decimal
    price: Decimal | None
    idempotency_key: str


@dataclass(frozen=True, kw_only=True)
class TradeExecuted(DomainEvent):
    """
    Emitted after each fill is confirmed and recorded.

    One TradeExecuted event is emitted per fill (not per order), since an
    order can be partially filled multiple times.

    Consumers:
    - Notification service: "Your BTC order filled at R$ 290,250".
    - Tax reporting service: record realized gains/losses.
    - Analytics: trade volume and price impact tracking.
    - Portfolio service: invalidate cached portfolio snapshots.
    """

    order_id: uuid.UUID
    execution_id: uuid.UUID
    user_id: uuid.UUID
    asset_id: uuid.UUID
    side: str
    executed_price: Decimal
    executed_amount: Decimal
    fee: Decimal
    fill_value: Decimal  # executed_price * executed_amount (quote currency)
    external_fill_id: str | None


@dataclass(frozen=True, kw_only=True)
class OrderFailed(DomainEvent):
    """
    Emitted when an order transitions to FAILED status.

    Consumers:
    - Notification service: alert user of failure.
    - Reconciliation job: investigate external gateway state.
    """

    order_id: uuid.UUID
    user_id: uuid.UUID
    reason: str
    idempotency_key: str


@dataclass(frozen=True, kw_only=True)
class OrderCancelled(DomainEvent):
    """Emitted when an open order is cancelled (user-initiated or system)."""

    order_id: uuid.UUID
    user_id: uuid.UUID
    reason: str

from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class TransactionType(str, enum.Enum):
    """
    High-level classification of the fund movement.

    DEPOSIT   – funds entering the platform from an external bank account.
    WITHDRAW  – funds leaving the platform to an external bank account.
    TRADE     – internal transfer between fiat and asset accounts (generated
                by a TradeExecution).
    FEE       – platform or network fee charged to the user.
    """

    DEPOSIT = "DEPOSIT"
    WITHDRAW = "WITHDRAW"
    TRADE = "TRADE"
    FEE = "FEE"


class TransactionStatus(str, enum.Enum):
    """
    Transaction lifecycle state.

    PENDING    – created, awaiting external confirmation (e.g. bank webhook).
    PROCESSING – gateway call initiated; waiting for settlement.
    COMPLETED  – confirmed and ledger entries have been posted.
    FAILED     – external system returned an error or timed out.
    REVERSED   – completed transaction was reversed / refunded.
    """

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REVERSED = "REVERSED"

    @property
    def is_terminal(self) -> bool:
        return self in {TransactionStatus.COMPLETED, TransactionStatus.FAILED, TransactionStatus.REVERSED}


class Transaction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Represents a single fund-movement intent from the user's perspective.

    Each Transaction eventually results in one or more LedgerEntry pairs
    (double-entry). The Transaction acts as the externally visible record;
    the LedgerEntries are the internal accounting truth.

    ``reference_id`` stores the gateway-side identifier for reconciliation
    (e.g. a PIX transaction ID, Stripe charge ID, or exchange withdrawal ID).

    Async deposit / withdrawal flow
    --------------------------------
    1. Service creates Transaction with status=PENDING.
    2. Service calls BankingGateway and stores the gateway reference.
    3. A webhook / polling job confirms the transfer and calls
       BankingService.confirm_deposit(), which:
           a. Creates the LedgerEntry pair.
           b. Updates Transaction.status → COMPLETED.

    This design allows the platform to reconcile in-flight transactions
    even after a process restart (Outbox Pattern — see banking_service.py).
    """

    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_user_id_status", "user_id", "status"),
        Index("ix_transactions_reference_id", "reference_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    transaction_type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType, name="transaction_type_enum"),
        nullable=False,
    )
    status: Mapped[TransactionStatus] = mapped_column(
        Enum(TransactionStatus, name="transaction_status_enum"),
        nullable=False,
        default=TransactionStatus.PENDING,
        index=True,
    )
    # Gateway-provided identifier for external reconciliation.
    reference_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped[User] = relationship("User", back_populates="transactions")

    def __repr__(self) -> str:
        return (
            f"<Transaction id={self.id} type={self.transaction_type}"
            f" status={self.status} ref={self.reference_id!r}>"
        )

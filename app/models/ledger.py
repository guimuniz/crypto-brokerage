from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.order import AMOUNT_PRECISION, AMOUNT_SCALE

if TYPE_CHECKING:
    from app.models.account import Account


class LedgerEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Immutable double-entry accounting record.

    ╔══════════════════════════════════════════════════════════════════╗
    ║  CRITICAL — READ BEFORE TOUCHING THIS MODEL                     ║
    ╠══════════════════════════════════════════════════════════════════╣
    ║  Every financial event MUST produce exactly ONE LedgerEntry     ║
    ║  where:                                                          ║
    ║      amount debited from debit_account  ==                      ║
    ║      amount credited to  credit_account                         ║
    ║                                                                  ║
    ║  This invariant (debits == credits) is the foundation of the    ║
    ║  double-entry accounting system and must NEVER be violated.     ║
    ║                                                                  ║
    ║  Rows in this table are APPEND-ONLY. Never UPDATE or DELETE.    ║
    ║  Reversals are recorded as new, opposing LedgerEntries.         ║
    ╚══════════════════════════════════════════════════════════════════╝

    Field semantics
    ---------------
    debit_account_id  : account whose balance DECREASES (source of funds).
    credit_account_id : account whose balance INCREASES (destination of funds).
    amount            : the moved quantity — always positive.
    currency          : the denomination (ISO 4217 or crypto ticker).
    reference_type    : what business event created this entry
                        (e.g. "DEPOSIT", "TRADE", "FEE").
    reference_id      : foreign key into the originating entity
                        (Transaction.id, Order.id, etc.) stored as a string
                        to allow cross-entity references without an FK.

    Balance derivation
    ------------------
    Account balance = SUM(credit entries) - SUM(debit entries) for that account.
    See AccountRepository.get_balance() for the canonical query.
    """

    __tablename__ = "ledger_entries"
    __table_args__ = (
        # Fast balance lookup: filter by account, aggregate amount.
        Index("ix_ledger_debit_account_id", "debit_account_id"),
        Index("ix_ledger_credit_account_id", "credit_account_id"),
        # Reconciliation: find all entries for a given business event.
        Index("ix_ledger_reference", "reference_type", "reference_id"),
    )

    debit_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    credit_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Amount must be positive; direction is encoded by debit/credit accounts.
    amount: Mapped[Decimal] = mapped_column(
        Numeric(AMOUNT_PRECISION, AMOUNT_SCALE),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    # Human-readable category for auditing and reporting.
    reference_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # UUID or string ID of the originating entity (Transaction, Order, etc.)
    reference_id: Mapped[str] = mapped_column(String(128), nullable=False)

    # ── Relationships ─────────────────────────────────────────────────────────
    debit_account: Mapped[Account] = relationship(
        "Account",
        foreign_keys=[debit_account_id],
        back_populates="debit_entries",
    )
    credit_account: Mapped[Account] = relationship(
        "Account",
        foreign_keys=[credit_account_id],
        back_populates="credit_entries",
    )

    def __repr__(self) -> str:
        return (
            f"<LedgerEntry id={self.id}"
            f" debit={self.debit_account_id} → credit={self.credit_account_id}"
            f" amount={self.amount} {self.currency}"
            f" ref={self.reference_type}/{self.reference_id}>"
        )

from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.ledger import LedgerEntry
    from app.models.user import User


class AccountType(str, enum.Enum):
    """
    Logical account types used for ledger classification.

    FIAT accounts hold currency balances (BRL, USD, EUR).
    CRYPTO accounts hold digital asset balances.
    RESERVE accounts are internal/system accounts (fees, float, etc.).
    """

    FIAT = "FIAT"
    CRYPTO = "CRYPTO"
    RESERVE = "RESERVE"  # internal / system accounts


class BankAccountStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    REJECTED = "REJECTED"


class Account(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Logical account used as the unit of accounting in the ledger.

    ⚠️  IMPORTANT — NO BALANCE FIELD.
    The current balance is ALWAYS derived by querying LedgerEntries:

        SELECT SUM(credit_amount) - SUM(debit_amount)
        FROM ledger_entries
        WHERE account_id = :id

    Storing a denormalized balance would introduce race conditions and diverge
    from the ledger — the source of truth. See AccountRepository.get_balance().
    """

    __tablename__ = "accounts"
    __table_args__ = (
        # One account per currency per user is the default constraint.
        # Override if multi-currency per user is needed.
        UniqueConstraint("user_id", "currency", name="uq_accounts_user_currency"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    currency: Mapped[str] = mapped_column(
        String(10),  # e.g. "BRL", "USD", "BTC", "ETH"
        nullable=False,
    )
    account_type: Mapped[AccountType] = mapped_column(
        Enum(AccountType, name="account_type_enum"),
        nullable=False,
        default=AccountType.FIAT,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped[User] = relationship("User", back_populates="accounts")
    debit_entries: Mapped[list[LedgerEntry]] = relationship(
        "LedgerEntry",
        foreign_keys="LedgerEntry.debit_account_id",
        back_populates="debit_account",
        lazy="select",
    )
    credit_entries: Mapped[list[LedgerEntry]] = relationship(
        "LedgerEntry",
        foreign_keys="LedgerEntry.credit_account_id",
        back_populates="credit_account",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<Account id={self.id} user_id={self.user_id} currency={self.currency!r}>"


class BankAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    External bank account linked by the user for deposits and withdrawals.

    ``external_reference`` is the identifier returned by the BankingGateway
    (e.g. a PIX key, IBAN, or bank-specific account ID).
    """

    __tablename__ = "bank_accounts"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    bank_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[BankAccountStatus] = mapped_column(
        Enum(BankAccountStatus, name="bank_account_status_enum"),
        nullable=False,
        default=BankAccountStatus.PENDING,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped[User] = relationship("User", back_populates="bank_accounts")

    def __repr__(self) -> str:
        return (
            f"<BankAccount id={self.id} user_id={self.user_id}"
            f" bank={self.bank_name!r} status={self.status}>"
        )

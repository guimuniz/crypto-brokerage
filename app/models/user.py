from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.account import Account, BankAccount
    from app.models.order import Order, Position
    from app.models.transaction import Transaction


class KYCStatus(str, enum.Enum):
    """
    Know-Your-Customer verification state.

    State machine: PENDING → APPROVED | REJECTED
    Only APPROVED users may trade or withdraw funds.
    """

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Core identity entity — stores only authentication-related fields.

    Profile data (name, tax ID, KYC) is intentionally separated into
    UserProfile to honour the Single Responsibility Principle and to allow
    the auth subsystem to evolve independently of compliance requirements.
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(254), nullable=False, index=True, unique=True)
    hashed_password: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    profile: Mapped[UserProfile | None] = relationship(
        "UserProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin",  # always load profile with user
    )
    accounts: Mapped[list[Account]] = relationship(
        "Account",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    bank_accounts: Mapped[list[BankAccount]] = relationship(
        "BankAccount",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="select",
    )
    orders: Mapped[list[Order]] = relationship(
        "Order",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="select",
    )
    transactions: Mapped[list[Transaction]] = relationship(
        "Transaction",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="select",
    )
    positions: Mapped[list[Position]] = relationship(
        "Position",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"


class UserProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Extended user information required for compliance / KYC purposes.

    Separated from User to keep auth lean and allow independent iteration
    of the compliance data model.
    """

    __tablename__ = "user_profiles"
    __table_args__ = (UniqueConstraint("user_id", name="uq_user_profiles_user_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # tax_id stores CPF, CNPJ, SSN, etc. — encrypted at rest in production.
    tax_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    kyc_status: Mapped[KYCStatus] = mapped_column(
        Enum(KYCStatus, name="kyc_status_enum"),
        nullable=False,
        default=KYCStatus.PENDING,
    )
    country: Mapped[str] = mapped_column(
        String(2),  # ISO 3166-1 alpha-2
        nullable=False,
        default="BR",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped[User] = relationship("User", back_populates="profile")

    def __repr__(self) -> str:
        return (
            f"<UserProfile user_id={self.user_id} name={self.full_name!r}"
            f" kyc={self.kyc_status}>"
        )

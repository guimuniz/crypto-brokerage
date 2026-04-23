from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from sqlalchemy import Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.order import Order, Position


class AssetType(str, enum.Enum):
    """Broad classification of tradeable instruments."""

    CRYPTO = "CRYPTO"       # e.g. BTC, ETH, SOL
    FIAT = "FIAT"           # e.g. USD, BRL (used as quote currency)
    STOCK = "STOCK"         # tokenised equity (future)
    COMMODITY = "COMMODITY" # tokenised commodity (future)


class Asset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Tradeable instrument definition.

    ``precision`` defines the maximum number of decimal places accepted for
    this asset (e.g. BTC = 8, ETH = 18, BRL = 2). It is used to validate
    order amounts and to correctly display balances in the UI.

    ``network`` / ``blockchain`` records the settlement network for crypto
    assets (e.g. "ethereum", "solana", "bitcoin") to route withdrawals
    correctly and display the right explorer links.
    """

    __tablename__ = "assets"

    symbol: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        unique=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    asset_type: Mapped[AssetType] = mapped_column(
        Enum(AssetType, name="asset_type_enum"),
        nullable=False,
    )
    # Network / blockchain for routing on-chain withdrawals.
    # NULL for fiat assets.
    network: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Maximum decimal places (e.g. BTC=8, ETH=18, BRL=2)
    precision: Mapped[int] = mapped_column(Integer, nullable=False, default=8)

    # ── Relationships ─────────────────────────────────────────────────────────
    orders: Mapped[list[Order]] = relationship(
        "Order", back_populates="asset", lazy="select"
    )
    positions: Mapped[list[Position]] = relationship(
        "Position", back_populates="asset", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Asset symbol={self.symbol!r} type={self.asset_type} network={self.network!r}>"

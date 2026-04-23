"""
SQLAlchemy model registry.

Importing this module ensures all models are registered with
``Base.metadata`` so Alembic's autogenerate can discover every table.
"""

from app.models.account import Account, AccountType, BankAccount, BankAccountStatus
from app.models.asset import Asset, AssetType
from app.models.base import Base
from app.models.ledger import LedgerEntry
from app.models.order import Order, OrderSide, OrderStatus, OrderType, Position, TradeExecution
from app.models.transaction import Transaction, TransactionStatus, TransactionType
from app.models.user import KYCStatus, User, UserProfile

__all__ = [
    "Base",
    # User
    "User",
    "UserProfile",
    "KYCStatus",
    # Account
    "Account",
    "AccountType",
    "BankAccount",
    "BankAccountStatus",
    # Asset
    "Asset",
    "AssetType",
    # Order / Trade
    "Order",
    "OrderSide",
    "OrderType",
    "OrderStatus",
    "TradeExecution",
    "Position",
    # Transaction
    "Transaction",
    "TransactionType",
    "TransactionStatus",
    # Ledger
    "LedgerEntry",
]

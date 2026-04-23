"""
Simple result types returned by service methods.

These are plain dataclasses (not Pydantic models) so that services
remain independent of the API layer and avoid circular imports.
The API routers convert these to Pydantic response schemas.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.models.transaction import TransactionStatus


@dataclass
class UserRegistrationResult:
    user_id: uuid.UUID
    account_id: uuid.UUID


@dataclass
class BankAccountLinkResult:
    bank_account_id: uuid.UUID


@dataclass
class DepositResult:
    transaction_id: uuid.UUID
    external_transfer_id: str
    status: TransactionStatus


@dataclass
class WithdrawResult:
    transaction_id: uuid.UUID
    external_transfer_id: str
    status: TransactionStatus

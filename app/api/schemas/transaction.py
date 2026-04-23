from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.transaction import TransactionStatus, TransactionType


class TransactionRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    user_id: uuid.UUID
    transaction_type: TransactionType
    status: TransactionStatus
    reference_id: str | None
    created_at: datetime


class DepositResult(BaseModel):
    transaction_id: uuid.UUID
    external_transfer_id: str
    status: TransactionStatus


class WithdrawResult(BaseModel):
    transaction_id: uuid.UUID
    external_transfer_id: str
    status: TransactionStatus

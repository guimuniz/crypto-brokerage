from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.account import AccountType, BankAccountStatus


class AccountRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    user_id: uuid.UUID
    currency: str
    account_type: AccountType
    # Balance is NOT stored on the model — it is derived by the service layer
    # from LedgerEntries and injected here for the API response.
    balance: Decimal = Field(default=Decimal("0"), description="Derived from ledger entries")


class BankAccountCreate(BaseModel):
    external_reference: str = Field(
        min_length=1, max_length=255,
        description="PIX key, IBAN, or bank-specific account identifier"
    )
    bank_name: str = Field(min_length=1, max_length=100)


class BankAccountRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    user_id: uuid.UUID
    external_reference: str
    bank_name: str
    status: BankAccountStatus


class BankAccountLinkResult(BaseModel):
    model_config = {"from_attributes": True}

    bank_account_id: uuid.UUID

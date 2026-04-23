from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.deps import BankingGatewayDep, CurrentUser, DbSession
from app.api.schemas.account import (
    AccountRead,
    BankAccountCreate,
    BankAccountLinkResult,
    BankAccountRead,
)
from app.core.exceptions import BankAccountAlreadyLinkedError
from app.repositories.account_repository import AccountRepository, BankAccountRepository
from app.services.onboarding_service import OnboardingService

router = APIRouter(prefix="/accounts", tags=["Accounts"])


@router.get(
    "",
    response_model=list[AccountRead],
    summary="List all accounts for the authenticated user",
)
async def list_accounts(
    current_user: CurrentUser,
    db: DbSession,
) -> list[AccountRead]:
    """
    Return all platform accounts (fiat and crypto) with their derived balances.

    Balances are computed by querying LedgerEntries — they are never stored
    directly on the Account model.
    """
    repo = AccountRepository(db)
    accounts = await repo.list_by_user(current_user.id)

    result = []
    for account in accounts:
        balance = await repo.get_balance(account.id)
        result.append(
            AccountRead(
                id=account.id,
                user_id=account.user_id,
                currency=account.currency,
                account_type=account.account_type,
                balance=balance,
            )
        )
    return result


@router.get(
    "/{account_id}/balance",
    response_model=AccountRead,
    summary="Get balance for a specific account",
)
async def get_balance(
    account_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> AccountRead:
    repo = AccountRepository(db)
    account = await repo.get_by_id(account_id)

    if account is None or account.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_id} not found.",
        )

    balance = await repo.get_balance(account.id)
    return AccountRead(
        id=account.id,
        user_id=account.user_id,
        currency=account.currency,
        account_type=account.account_type,
        balance=balance,
    )


@router.post(
    "/bank-accounts",
    response_model=BankAccountLinkResult,
    status_code=status.HTTP_201_CREATED,
    summary="Link an external bank account",
)
async def link_bank_account(
    payload: BankAccountCreate,
    current_user: CurrentUser,
    db: DbSession,
    banking_gateway: BankingGatewayDep,
) -> BankAccountLinkResult:
    """
    Validate and link an external bank account (PIX key, IBAN, etc.)
    to the authenticated user's profile.
    """
    service = OnboardingService(session=db, banking_gateway=banking_gateway)
    try:
        result = await service.link_bank_account(
            user_id=current_user.id,
            external_reference=payload.external_reference,
            bank_name=payload.bank_name,
        )
        return BankAccountLinkResult(bank_account_id=result.bank_account_id)
    except BankAccountAlreadyLinkedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=exc.message,
        ) from exc


@router.get(
    "/bank-accounts",
    response_model=list[BankAccountRead],
    summary="List linked bank accounts",
)
async def list_bank_accounts(
    current_user: CurrentUser,
    db: DbSession,
) -> list[BankAccountRead]:
    repo = BankAccountRepository(db)
    bank_accounts = await repo.get_by_user(current_user.id)
    return [BankAccountRead.model_validate(ba) for ba in bank_accounts]

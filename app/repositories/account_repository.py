from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account, AccountType, BankAccount, BankAccountStatus
from app.models.ledger import LedgerEntry
from app.repositories.base import BaseRepository


class AccountRepository(BaseRepository[Account]):
    model = Account

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_by_user_and_currency(
        self, user_id: uuid.UUID, currency: str
    ) -> Account | None:
        result = await self._session.execute(
            select(Account).where(
                Account.user_id == user_id,
                Account.currency == currency,
            )
        )
        return result.scalars().first()

    async def get_balance(self, account_id: uuid.UUID) -> Decimal:
        """
        Derive the current balance from LedgerEntries (double-entry).

        Balance = SUM(credit_entries.amount) - SUM(debit_entries.amount)

        ⚠️  This query does NOT lock any rows. Use ``get_balance_for_update``
        before any debit operation to prevent concurrent overdraft.
        """
        credit_sum = await self._session.execute(
            select(func.coalesce(func.sum(LedgerEntry.amount), Decimal("0"))).where(
                LedgerEntry.credit_account_id == account_id
            )
        )
        debit_sum = await self._session.execute(
            select(func.coalesce(func.sum(LedgerEntry.amount), Decimal("0"))).where(
                LedgerEntry.debit_account_id == account_id
            )
        )
        credits: Decimal = credit_sum.scalar_one()
        debits: Decimal = debit_sum.scalar_one()
        return credits - debits

    async def get_balance_for_update(self, account_id: uuid.UUID) -> tuple[Account, Decimal]:
        """
        Acquire a row-level lock on the Account row, then derive balance.

        ⚠️  MUST be called within an active database transaction.
        The lock is held until the transaction commits or rolls back.

        Pattern:
            async with session.begin():
                account, balance = await repo.get_balance_for_update(account_id)
                if balance < required_amount:
                    raise InsufficientFundsError(...)
                # ... create LedgerEntries ...
                # Lock is released on commit.

        Using SELECT FOR UPDATE prevents race conditions where two concurrent
        requests read the same balance and both proceed to debit, resulting
        in a negative balance (overdraft).
        """
        result = await self._session.execute(
            select(Account)
            .where(Account.id == account_id)
            .with_for_update()  # SELECT FOR UPDATE — row-level lock
        )
        account = result.scalars().first()
        if account is None:
            from app.core.exceptions import AccountNotFoundError
            raise AccountNotFoundError(f"Account {account_id} not found.")

        balance = await self.get_balance(account_id)
        return account, balance

    async def create_default_account(
        self, user_id: uuid.UUID, currency: str, account_type: AccountType = AccountType.FIAT
    ) -> Account:
        account = Account(user_id=user_id, currency=currency, account_type=account_type)
        return await self.add(account)

    async def list_by_user(self, user_id: uuid.UUID) -> list[Account]:
        result = await self._session.execute(
            select(Account).where(Account.user_id == user_id)
        )
        return list(result.scalars().all())


class BankAccountRepository(BaseRepository[BankAccount]):
    model = BankAccount

    async def get_by_user(self, user_id: uuid.UUID) -> list[BankAccount]:
        result = await self._session.execute(
            select(BankAccount).where(BankAccount.user_id == user_id)
        )
        return list(result.scalars().all())

    async def get_by_external_reference(
        self, user_id: uuid.UUID, external_reference: str
    ) -> BankAccount | None:
        result = await self._session.execute(
            select(BankAccount).where(
                BankAccount.user_id == user_id,
                BankAccount.external_reference == external_reference,
            )
        )
        return result.scalars().first()

    async def activate(self, bank_account: BankAccount) -> BankAccount:
        return await self.update(bank_account, status=BankAccountStatus.ACTIVE)

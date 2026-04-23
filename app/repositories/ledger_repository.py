from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ledger import LedgerEntry
from app.repositories.base import BaseRepository


class LedgerRepository(BaseRepository[LedgerEntry]):
    model = LedgerEntry

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def create_double_entry(
        self,
        *,
        debit_account_id: uuid.UUID,
        credit_account_id: uuid.UUID,
        amount: Decimal,
        currency: str,
        reference_type: str,
        reference_id: str,
    ) -> LedgerEntry:
        """
        Record a balanced double-entry movement.

        Rules enforced here:
        - amount must be positive (direction is captured by debit/credit accounts).
        - debit_account_id != credit_account_id (a transfer to yourself is a no-op).
        - Both accounts are expected to use the same currency (validated by caller).

        The caller is responsible for:
        - Ensuring both accounts exist.
        - Committing the transaction (or relying on the request-level commit).
        - Calling this inside a transaction that also holds the lock obtained
          via AccountRepository.get_balance_for_update() for debit operations.

        Reference types (use these constants for consistency):
            "DEPOSIT"  — BankingService.deposit_funds
            "WITHDRAW" — BankingService.withdraw_funds
            "TRADE"    — TradingService.execute_trade
            "FEE"      — fee collection
        """
        if amount <= Decimal("0"):
            from app.core.exceptions import LedgerImbalanceError
            raise LedgerImbalanceError("LedgerEntry amount must be positive.")

        if debit_account_id == credit_account_id:
            from app.core.exceptions import LedgerImbalanceError
            raise LedgerImbalanceError("Debit and credit accounts must be different.")

        entry = LedgerEntry(
            debit_account_id=debit_account_id,
            credit_account_id=credit_account_id,
            amount=amount,
            currency=currency,
            reference_type=reference_type,
            reference_id=str(reference_id),
        )
        return await self.add(entry)

    async def get_entries_for_account(
        self,
        account_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[LedgerEntry]:
        """
        Return ledger entries where the account appears on either side.
        Results are ordered most-recent first for statement generation.
        """
        result = await self._session.execute(
            select(LedgerEntry)
            .where(
                (LedgerEntry.debit_account_id == account_id)
                | (LedgerEntry.credit_account_id == account_id)
            )
            .order_by(LedgerEntry.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_entries_by_reference(
        self, reference_type: str, reference_id: str
    ) -> list[LedgerEntry]:
        """Return all ledger entries linked to a specific business event."""
        result = await self._session.execute(
            select(LedgerEntry).where(
                LedgerEntry.reference_type == reference_type,
                LedgerEntry.reference_id == reference_id,
            )
        )
        return list(result.scalars().all())

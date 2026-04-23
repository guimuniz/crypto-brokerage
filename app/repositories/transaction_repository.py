from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction, TransactionStatus, TransactionType
from app.repositories.base import BaseRepository


class TransactionRepository(BaseRepository[Transaction]):
    model = Transaction

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        transaction_type: TransactionType,
        reference_id: str | None = None,
    ) -> Transaction:
        txn = Transaction(
            user_id=user_id,
            transaction_type=transaction_type,
            status=TransactionStatus.PENDING,
            reference_id=reference_id,
        )
        return await self.add(txn)

    async def update_status(
        self,
        transaction: Transaction,
        status: TransactionStatus,
        reference_id: str | None = None,
    ) -> Transaction:
        kwargs: dict = {"status": status}
        if reference_id is not None:
            kwargs["reference_id"] = reference_id
        return await self.update(transaction, **kwargs)

    async def get_by_reference(
        self, reference_id: str
    ) -> Transaction | None:
        result = await self._session.execute(
            select(Transaction).where(Transaction.reference_id == reference_id)
        )
        return result.scalars().first()

    async def get_by_user(
        self,
        user_id: uuid.UUID,
        *,
        status: TransactionStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Transaction]:
        query = select(Transaction).where(Transaction.user_id == user_id)
        if status is not None:
            query = query.where(Transaction.status == status)
        query = query.order_by(Transaction.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_pending(self) -> list[Transaction]:
        """
        Return all PENDING transactions.

        Used by the reconciliation job to re-check gateway status for
        transactions that never received a webhook callback.
        """
        result = await self._session.execute(
            select(Transaction).where(Transaction.status == TransactionStatus.PENDING)
        )
        return list(result.scalars().all())

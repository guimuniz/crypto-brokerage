from __future__ import annotations

import uuid
from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """
    Generic async CRUD repository.

    Provides a consistent interface for common database operations.
    Domain-specific repositories inherit from this and add query methods
    tailored to their model.

    Usage::

        class UserRepository(BaseRepository[User]):
            model = User
    """

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, entity_id: uuid.UUID) -> ModelT | None:
        """Return the entity with *entity_id*, or None if not found."""
        return await self._session.get(self.model, entity_id)

    async def get_all(self, *, limit: int = 100, offset: int = 0) -> list[ModelT]:
        """Return a page of entities ordered by primary key."""
        result = await self._session.execute(
            select(self.model).order_by(self.model.id).limit(limit).offset(offset)  # type: ignore[attr-defined]
        )
        return list(result.scalars().all())

    async def add(self, entity: ModelT) -> ModelT:
        """
        Persist a new entity.

        The caller must commit (or rely on the request-level commit in
        ``get_db``) for the write to become durable.
        """
        self._session.add(entity)
        await self._session.flush()  # flush to get DB-generated defaults (e.g. id)
        await self._session.refresh(entity)
        return entity

    async def update(self, entity: ModelT, **kwargs: Any) -> ModelT:
        """Apply *kwargs* as attribute updates and flush."""
        for key, value in kwargs.items():
            setattr(entity, key, value)
        await self._session.flush()
        await self._session.refresh(entity)
        return entity

    async def delete(self, entity: ModelT) -> None:
        """Mark *entity* for deletion and flush."""
        await self._session.delete(entity)
        await self._session.flush()

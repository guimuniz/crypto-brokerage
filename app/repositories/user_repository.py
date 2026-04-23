from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import KYCStatus, User, UserProfile
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._profile_repo = UserProfileRepository(session)

    async def get_by_email(self, email: str) -> User | None:
        """Case-insensitive email lookup (emails are stored lowercase)."""
        result = await self._session.execute(
            select(User).where(User.email == email.lower())
        )
        return result.scalars().first()

    async def create_with_profile(
        self,
        *,
        email: str,
        hashed_password: str,
        full_name: str,
        country: str,
        tax_id: str | None = None,
    ) -> User:
        """
        Create a User and its associated UserProfile atomically.

        The caller is responsible for committing the transaction.
        Both entities are flushed (but not committed) within this method
        so that ``user.id`` is available when creating the profile.
        """
        user = User(
            email=email.lower(),
            hashed_password=hashed_password,
            is_active=True,
        )
        await self.add(user)

        profile = UserProfile(
            user_id=user.id,
            full_name=full_name,
            tax_id=tax_id,
            kyc_status=KYCStatus.PENDING,
            country=country,
        )
        await self._profile_repo.add(profile)

        return user

    async def exists_by_email(self, email: str) -> bool:
        result = await self._session.execute(
            select(User.id).where(User.email == email.lower()).limit(1)
        )
        return result.scalar() is not None


class UserProfileRepository(BaseRepository[UserProfile]):
    model = UserProfile

    async def get_by_user_id(self, user_id: uuid.UUID) -> UserProfile | None:
        result = await self._session.execute(
            select(UserProfile).where(UserProfile.user_id == user_id)
        )
        return result.scalars().first()

    async def update_kyc_status(
        self, user_id: uuid.UUID, status: KYCStatus
    ) -> UserProfile | None:
        profile = await self.get_by_user_id(user_id)
        if profile is not None:
            await self.update(profile, kyc_status=status)
        return profile

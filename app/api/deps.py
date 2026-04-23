from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AuthenticationError, UserNotFoundError
from app.core.security import decode_token
from app.integrations.banking_gateway import HttpBankingGateway
from app.integrations.base import BankingGateway, ExchangeGateway
from app.integrations.exchange_gateway import HttpExchangeGateway
from app.models.user import User
from app.repositories.user_repository import UserRepository

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


# ── Database session ──────────────────────────────────────────────────────────

DbSession = Annotated[AsyncSession, Depends(get_db)]


# ── Current user ──────────────────────────────────────────────────────────────

async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: DbSession,
) -> User:
    """
    Decode the JWT bearer token and return the authenticated User.

    :raises HTTPException 401: if the token is missing, expired, or invalid.
    :raises HTTPException 401: if the user referenced in the token no longer exists.
    :raises HTTPException 403: if the user account is inactive.
    """
    try:
        payload = decode_token(token)
        user_id_str: str | None = payload.get("sub")
        if user_id_str is None:
            raise AuthenticationError("Token missing 'sub' claim.")
        user_id = uuid.UUID(user_id_str)
    except (AuthenticationError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated.",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


# ── Gateway dependencies ──────────────────────────────────────────────────────


async def get_exchange_gateway() -> ExchangeGateway:
    """Provide the exchange gateway implementation."""
    return HttpExchangeGateway()


async def get_banking_gateway() -> BankingGateway:
    """Provide the banking gateway implementation."""
    return HttpBankingGateway()


ExchangeGatewayDep = Annotated[ExchangeGateway, Depends(get_exchange_gateway)]
BankingGatewayDep = Annotated[BankingGateway, Depends(get_banking_gateway)]

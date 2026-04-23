from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from typing import Annotated
from fastapi import Depends

from app.api.deps import BankingGatewayDep, DbSession
from app.api.schemas.user import TokenResponse, UserCreate, UserRead, UserRegistrationResult
from app.core.exceptions import UserAlreadyExistsError
from app.core.security import create_access_token, create_refresh_token, verify_password
from app.repositories.user_repository import UserRepository
from app.services.onboarding_service import OnboardingService

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/register",
    response_model=UserRegistrationResult,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description=(
        "Creates a User, UserProfile (KYC=PENDING), and a default fiat account. "
        "Returns the new user_id and account_id."
    ),
)
async def register(
    payload: UserCreate,
    db: DbSession,
    banking_gateway: BankingGatewayDep,
) -> UserRegistrationResult:
    service = OnboardingService(session=db, banking_gateway=banking_gateway)
    try:
        result = await service.register_user(
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
            country=payload.country,
            tax_id=payload.tax_id,
        )
        return UserRegistrationResult(user_id=result.user_id, account_id=result.account_id)
    except UserAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=exc.message,
        ) from exc


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and obtain JWT tokens",
)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DbSession,
) -> TokenResponse:
    """
    Authenticate with email + password and return access + refresh JWT tokens.

    The access token expires after ``settings.jwt_access_token_expire_minutes``.
    The refresh token expires after ``settings.jwt_refresh_token_expire_days``.
    """
    repo = UserRepository(db)
    user = await repo.get_by_email(form_data.username)  # OAuth2 uses 'username' field

    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated.",
        )

    return TokenResponse(
        access_token=create_access_token(subject=str(user.id)),
        refresh_token=create_refresh_token(subject=str(user.id)),
    )


@router.get(
    "/me",
    response_model=UserRead,
    summary="Get the authenticated user's profile",
)
async def get_me(
    db: DbSession,
    # Import here to avoid circular dependency at module level
) -> UserRead:
    """
    Return the currently authenticated user's information.

    This endpoint is protected — the bearer token must be provided.
    """
    # TODO: Use CurrentUser dependency. Placed here as a stub endpoint.
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Use the Authorization header with a valid bearer token.",
    )

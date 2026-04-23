from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.user import KYCStatus


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    country: str = Field(min_length=2, max_length=2, description="ISO 3166-1 alpha-2 country code")
    tax_id: str | None = Field(default=None, max_length=64)

    @field_validator("country")
    @classmethod
    def uppercase_country(cls, v: str) -> str:
        return v.upper()


class UserRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    email: str
    is_active: bool
    created_at: datetime


class UserProfileRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    user_id: uuid.UUID
    full_name: str
    kyc_status: KYCStatus
    country: str


class UserWithProfileRead(UserRead):
    profile: UserProfileRead | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserRegistrationResult(BaseModel):
    """API response for POST /auth/register. Mirrors services.result_types.UserRegistrationResult."""

    model_config = {"from_attributes": True}

    user_id: uuid.UUID
    account_id: uuid.UUID

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import (
    UserAlreadyExistsError,
    BankAccountAlreadyLinkedError,
)
from app.core.security import hash_password
from app.integrations.base import BankingGateway
from app.models.account import AccountType, BankAccountStatus
from app.repositories.account_repository import AccountRepository, BankAccountRepository
from app.repositories.user_repository import UserRepository
from app.services.result_types import BankAccountLinkResult, UserRegistrationResult

logger = logging.getLogger(__name__)
settings = get_settings()


class OnboardingService:
    """
    Handles user registration and bank account linking.

    All methods are transactional — the caller (API layer) is responsible
    for committing via ``get_db``, which commits on success or rolls back
    on exception.
    """

    def __init__(
        self,
        session: AsyncSession,
        banking_gateway: BankingGateway,
    ) -> None:
        self._session = session
        self._banking_gateway = banking_gateway
        self._user_repo = UserRepository(session)
        self._account_repo = AccountRepository(session)
        self._bank_account_repo = BankAccountRepository(session)

    async def register_user(
        self,
        *,
        email: str,
        password: str,
        full_name: str,
        country: str,
        tax_id: str | None = None,
    ) -> "UserRegistrationResult":
        """
        Create a new user, profile, and default account atomically.

        Steps:
        1. Check for duplicate email (raises UserAlreadyExistsError).
        2. Hash password with bcrypt.
        3. Create User + UserProfile (KYC defaults to PENDING).
        4. Create the default fiat Account (currency from settings).

        The default account uses the platform's configured base currency
        (settings.default_account_currency). Additional accounts can be
        created later (e.g. CRYPTO accounts per asset).

        TODO: Emit UserRegistered domain event for downstream consumers
              (e.g. KYC verification service, welcome email job).
        """
        if await self._user_repo.exists_by_email(email):
            raise UserAlreadyExistsError(f"Email '{email}' is already registered.")

        user = await self._user_repo.create_with_profile(
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name,
            country=country,
            tax_id=tax_id,
        )

        # Create default fiat account — balance starts at zero (no ledger entries).
        account = await self._account_repo.create_default_account(
            user_id=user.id,
            currency=settings.default_account_currency,
            account_type=AccountType.FIAT,
        )

        logger.info("User registered: user_id=%s email=%s", user.id, email)

        return UserRegistrationResult(user_id=user.id, account_id=account.id)

    async def link_bank_account(
        self,
        *,
        user_id: uuid.UUID,
        external_reference: str,
        bank_name: str,
    ) -> BankAccountLinkResult:
        """
        Link an external bank account after validating it with the BankingGateway.

        Steps:
        1. Check for duplicate (same user + external_reference).
        2. Call BankingGateway to validate the account exists and is reachable.
        3. Persist the BankAccount with status=ACTIVE if validation succeeds,
           or status=PENDING if the gateway returns a PENDING verification.

        TODO: For PIX, ``external_reference`` is the PIX key (CPF, CNPJ, phone, or UUID).
        TODO: Add KYC check — only APPROVED users can link bank accounts.
        TODO: Emit BankAccountLinked domain event.
        """
        existing = await self._bank_account_repo.get_by_external_reference(
            user_id, external_reference
        )
        if existing is not None:
            raise BankAccountAlreadyLinkedError(
                f"Bank account '{external_reference}' is already linked."
            )

        # TODO: Call BankingGateway to validate the external account.
        #       For now, we optimistically mark it ACTIVE after the gateway call.
        #       In production, you may need to wait for a micro-deposit confirmation.
        try:
            # Validation ping — not all gateways support explicit validation.
            # Replace with: await self._banking_gateway.validate_account(external_reference)
            logger.info("Stub: validating bank account %s via gateway", external_reference)
        except Exception as exc:
            logger.error("Bank account validation failed: %s", exc)
            raise

        from app.models.account import BankAccount
        bank_account = BankAccount(
            user_id=user_id,
            external_reference=external_reference,
            bank_name=bank_name,
            status=BankAccountStatus.ACTIVE,
        )
        self._session.add(bank_account)
        await self._session.flush()
        await self._session.refresh(bank_account)

        logger.info(
            "Bank account linked: user_id=%s bank_account_id=%s ref=%s",
            user_id,
            bank_account.id,
            external_reference,
        )

        return BankAccountLinkResult(bank_account_id=bank_account.id)


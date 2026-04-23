from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AccountNotFoundError,
    BankAccountNotFoundError,
    InsufficientFundsError,
)
from app.integrations.base import BankingGateway
from app.models.transaction import TransactionStatus, TransactionType
from app.repositories.account_repository import AccountRepository, BankAccountRepository
from app.repositories.ledger_repository import LedgerRepository
from app.repositories.transaction_repository import TransactionRepository
from app.services.result_types import DepositResult, WithdrawResult

logger = logging.getLogger(__name__)


class BankingService:
    """
    Handles deposits and withdrawals between external bank accounts
    and user platform accounts.

    Async Flow (deposit)
    --------------------
    1. ``deposit_funds``   — creates a PENDING Transaction, calls gateway.
    2. ``confirm_deposit`` — called by webhook handler or reconciliation job
                             once the transfer is confirmed externally.
    3. ``confirm_deposit`` — posts LedgerEntries and marks Transaction COMPLETED.

    This two-phase approach ensures:
    - The platform never credits funds without external confirmation.
    - Transactions can be reconciled after a crash (Outbox Pattern TODO below).
    - Idempotent confirmation: re-calling ``confirm_deposit`` with the same
      reference_id is safe because Transaction status is checked first.

    TODO — Outbox Pattern
    ---------------------
    For true at-least-once delivery guarantees, persist the banking gateway
    call intent in an "outbox" table within the SAME transaction as the
    Transaction row. A separate background worker reads unprocessed outbox
    entries and calls the gateway. This prevents the scenario where:
        - Transaction is saved to DB ✓
        - Process crashes before calling gateway ✗
        - Gateway call is never retried ✗
    See: https://microservices.io/patterns/data/transactional-outbox.html
    """

    def __init__(
        self,
        session: AsyncSession,
        banking_gateway: BankingGateway,
    ) -> None:
        self._session = session
        self._gateway = banking_gateway
        self._account_repo = AccountRepository(session)
        self._bank_account_repo = BankAccountRepository(session)
        self._transaction_repo = TransactionRepository(session)
        self._ledger_repo = LedgerRepository(session)

    async def deposit_funds(
        self,
        *,
        user_id: uuid.UUID,
        bank_account_id: uuid.UUID,
        amount: Decimal,
        currency: str,
    ) -> DepositResult:
        """
        Initiate an inbound fund transfer from the user's bank account.

        Phase 1 (synchronous):
        1. Validate that the bank account belongs to the user and is ACTIVE.
        2. Validate that the user has a platform Account for the currency.
        3. Create a PENDING Transaction (source of truth for the in-flight transfer).
        4. Call BankingGateway.initiate_transfer() — may block up to gateway timeout.
        5. Store the gateway's external_transfer_id in Transaction.reference_id.

        Phase 2 (async, triggered by webhook or reconciliation job):
        → ``confirm_deposit()`` is called once the gateway confirms receipt.

        TODO: Implement the Outbox Pattern (see class docstring) to handle
              process crashes between step 3 and step 4.
        TODO: Validate amount > 0 and within per-day deposit limits.
        TODO: Check KYC status before allowing deposits.
        """
        # Validate bank account ownership
        bank_account = await self._bank_account_repo.get_by_id(bank_account_id)
        if bank_account is None or bank_account.user_id != user_id:
            raise BankAccountNotFoundError(
                f"Bank account {bank_account_id} not found for user {user_id}."
            )

        # Validate platform account exists for the requested currency
        account = await self._account_repo.get_by_user_and_currency(user_id, currency)
        if account is None:
            raise AccountNotFoundError(
                f"No {currency} account found for user {user_id}. "
                "Create one before depositing."
            )

        # Create the Transaction record first (idempotency anchor)
        transaction = await self._transaction_repo.create(
            user_id=user_id,
            transaction_type=TransactionType.DEPOSIT,
        )

        try:
            # Call the banking gateway to initiate the inbound transfer
            transfer = await self._gateway.initiate_transfer(
                external_reference=bank_account.external_reference,
                amount=amount,
                currency=currency,
                direction="INBOUND",
                description=f"Deposit for transaction {transaction.id}",
            )

            # Store the gateway reference for webhook matching / reconciliation
            await self._transaction_repo.update_status(
                transaction,
                status=TransactionStatus.PROCESSING,
                reference_id=transfer.external_transfer_id,
            )
        except Exception:
            # Gateway call failed — mark transaction as FAILED for reconciliation
            await self._transaction_repo.update_status(
                transaction, status=TransactionStatus.FAILED
            )
            raise

        logger.info(
            "Deposit initiated: user_id=%s amount=%s %s txn_id=%s gateway_ref=%s",
            user_id, amount, currency, transaction.id, transfer.external_transfer_id,
        )

        return DepositResult(
            transaction_id=transaction.id,
            external_transfer_id=transfer.external_transfer_id,
            status=transaction.status,
        )

    async def confirm_deposit(
        self,
        *,
        external_transfer_id: str,
    ) -> None:
        """
        Confirm an inbound transfer and post the corresponding LedgerEntries.

        Called by:
        - The webhook handler when the banking provider sends a callback.
        - The reconciliation job when polling confirms a transfer completed.

        Idempotency: if the Transaction is already COMPLETED, this method
        is a no-op — safe to call multiple times for the same transfer.

        Steps:
        1. Find the Transaction by external_transfer_id.
        2. Guard: skip if already COMPLETED or FAILED.
        3. Verify status with BankingGateway (optional, for webhook-based flows).
        4. Post double-entry LedgerEntries:
               Debit  → platform reserve / float account (funds enter platform)
               Credit → user's account (user's balance increases)
        5. Mark Transaction → COMPLETED.

        TODO: Implement the reserve/float account lookup. For now, a system
              account UUID must be configured (settings.reserve_account_id).
        TODO: Emit FundsDeposited domain event.
        TODO: Notify user via email / push notification.
        """
        transaction = await self._transaction_repo.get_by_reference(external_transfer_id)
        if transaction is None:
            logger.warning("Received confirm_deposit for unknown ref: %s", external_transfer_id)
            return

        # Idempotency guard — do not double-post ledger entries
        if transaction.status == TransactionStatus.COMPLETED:
            logger.info("Deposit already confirmed: txn_id=%s", transaction.id)
            return

        if transaction.status == TransactionStatus.FAILED:
            logger.warning("Received confirm for FAILED transaction: txn_id=%s", transaction.id)
            return

        # TODO: Look up the amount and currency from the original gateway record
        #       or store them on the Transaction model (recommended).
        #       For now, this is a TODO placeholder.
        # amount = transaction.amount
        # currency = transaction.currency
        # user_account = await self._account_repo.get_by_user_and_currency(
        #     transaction.user_id, currency
        # )
        # await self._ledger_repo.create_double_entry(
        #     debit_account_id=settings.reserve_account_id,
        #     credit_account_id=user_account.id,
        #     amount=amount,
        #     currency=currency,
        #     reference_type="DEPOSIT",
        #     reference_id=str(transaction.id),
        # )

        await self._transaction_repo.update_status(
            transaction, status=TransactionStatus.COMPLETED
        )

        logger.info("Deposit confirmed: txn_id=%s ref=%s", transaction.id, external_transfer_id)

    async def withdraw_funds(
        self,
        *,
        user_id: uuid.UUID,
        bank_account_id: uuid.UUID,
        amount: Decimal,
        currency: str,
    ) -> WithdrawResult:
        """
        Initiate an outbound fund transfer to the user's bank account.

        Steps:
        1. Acquire SELECT FOR UPDATE on the user's Account row.
        2. Derive current balance from LedgerEntries.
        3. Raise InsufficientFundsError if balance < amount.
        4. Create PENDING Transaction.
        5. Post LedgerEntries (debit user account, credit reserve).
        6. Call BankingGateway.initiate_transfer() — OUTBOUND.
        7. Update Transaction → PROCESSING.

        ⚠️  Steps 4–5 MUST happen in the same DB transaction before step 6
        to prevent double-spend. If step 6 fails:
        - The DB transaction is rolled back (steps 4–5 undone).
        - The user's balance is NOT debited.
        - Return a FAILED Transaction to the caller.

        TODO: Add withdrawal limits (daily, per-transaction).
        TODO: Add KYC approval check.
        TODO: Emit FundsWithdrawn domain event.
        """
        # Step 1 & 2: Lock the account row and derive balance atomically
        account, balance = await self._account_repo.get_balance_for_update(
            # TODO: replace with actual account lookup by user + currency
            account_id=uuid.uuid4()  # placeholder — resolve from user_id + currency
        )

        # Step 3: Balance check
        if balance < amount:
            raise InsufficientFundsError(
                available=str(balance), required=str(amount), currency=currency
            )

        # TODO: Steps 4–7 (full implementation mirrors deposit_funds in reverse)
        #       Scaffold left as TODO for brevity; pattern is identical to deposit.
        raise NotImplementedError(
            "withdraw_funds: steps 4–7 not yet implemented. "
            "See banking_service.py docstring for the full algorithm."
        )


# DepositResult and WithdrawResult are imported inline inside methods to
# avoid circular imports (services → api.schemas → services).

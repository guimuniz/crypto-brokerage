"""
Domain exception hierarchy for the brokerage platform.

All custom exceptions inherit from BrokerageError so callers can catch the
broad category when needed, or the specific subclass for precise handling.
HTTP mapping is done in the FastAPI exception handlers (app/main.py).
"""

from __future__ import annotations


# ── Base ──────────────────────────────────────────────────────────────────────


class BrokerageError(Exception):
    """Root exception for all domain errors."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.__class__.__name__


# ── Auth & Identity ───────────────────────────────────────────────────────────


class AuthenticationError(BrokerageError):
    """Invalid credentials or expired token."""


class AuthorizationError(BrokerageError):
    """Authenticated user lacks permission for the requested action."""


class UserNotFoundError(BrokerageError):
    """No user found for the given identifier."""


class UserAlreadyExistsError(BrokerageError):
    """Attempt to register a duplicate email."""


# ── KYC / Compliance ─────────────────────────────────────────────────────────


class KYCNotApprovedError(BrokerageError):
    """Operation requires KYC approval that has not been granted."""


# ── Account & Banking ─────────────────────────────────────────────────────────


class AccountNotFoundError(BrokerageError):
    """No account found for the given identifier."""


class BankAccountNotFoundError(BrokerageError):
    """External bank account not found."""


class BankAccountAlreadyLinkedError(BrokerageError):
    """The bank account is already linked to the user."""


class InsufficientFundsError(BrokerageError):
    """Account balance is too low to complete the requested operation."""

    def __init__(self, available: str, required: str, currency: str) -> None:
        super().__init__(
            f"Insufficient funds: available={available} {currency}, required={required} {currency}"
        )
        self.available = available
        self.required = required
        self.currency = currency


# ── Assets ────────────────────────────────────────────────────────────────────


class AssetNotFoundError(BrokerageError):
    """No asset found for the given identifier or symbol."""


# ── Trading ───────────────────────────────────────────────────────────────────


class DuplicateIdempotencyKeyError(BrokerageError):
    """
    An order with this idempotency key already exists.

    The caller should treat the existing order as the response rather than
    creating a new one.
    """

    def __init__(self, idempotency_key: str) -> None:
        super().__init__(
            f"An order with idempotency key '{idempotency_key}' already exists."
        )
        self.idempotency_key = idempotency_key


class OrderNotFoundError(BrokerageError):
    """No order found for the given identifier."""


class InvalidOrderError(BrokerageError):
    """Order parameters are invalid (e.g. zero amount, unsupported pair)."""


class OrderAlreadyFinalizedError(BrokerageError):
    """Attempt to modify an order that has already reached a terminal state."""


# ── Transactions & Ledger ─────────────────────────────────────────────────────


class TransactionNotFoundError(BrokerageError):
    """No transaction found for the given identifier."""


class LedgerImbalanceError(BrokerageError):
    """
    Double-entry integrity violation: debits do not equal credits.
    Should never be raised in production; indicates a programming error.
    """


# ── External Integrations ─────────────────────────────────────────────────────


class ExternalGatewayError(BrokerageError):
    """An external gateway (exchange, banking) returned an unexpected error."""

    def __init__(self, gateway: str, message: str, *, status_code: int | None = None) -> None:
        super().__init__(f"[{gateway}] {message}")
        self.gateway = gateway
        self.status_code = status_code


class ExternalGatewayTimeoutError(ExternalGatewayError):
    """Gateway did not respond within the configured timeout."""


class ExternalGatewayRateLimitError(ExternalGatewayError):
    """Gateway rejected the request due to rate limiting."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from decimal import Decimal


# ── Exchange Gateway ──────────────────────────────────────────────────────────


@dataclass
class InstrumentPrice:
    symbol: str
    bid: Decimal
    ask: Decimal
    last: Decimal
    timestamp: float  # Unix epoch seconds


@dataclass
class OrderSubmission:
    """Result returned by ExchangeGateway.submit_order()."""

    external_order_id: str
    status: str          # e.g. "OPEN", "FILLED", "PARTIALLY_FILLED", "REJECTED"
    filled_amount: Decimal = field(default_factory=lambda: Decimal("0"))
    average_price: Decimal = field(default_factory=lambda: Decimal("0"))
    fee: Decimal = field(default_factory=lambda: Decimal("0"))
    # Individual fill events (for partial fills).
    fills: list[FillEvent] = field(default_factory=list)


@dataclass
class FillEvent:
    """A single fill event from the exchange."""

    fill_id: str
    price: Decimal
    amount: Decimal
    fee: Decimal
    timestamp: float


@dataclass
class OrderStatusResponse:
    external_order_id: str
    status: str
    filled_amount: Decimal
    average_price: Decimal
    fills: list[FillEvent] = field(default_factory=list)


class ExchangeGateway(abc.ABC):
    """
    Abstract interface for the exchange integration.

    All methods are async to support HTTP-based implementations.
    Implementations must handle:
    - Authentication / request signing
    - Rate limiting (honour ``ExternalGatewayRateLimitError``)
    - Timeouts and retries (use tenacity in concrete implementations)
    - Idempotent order submission (pass ``client_order_id`` to exchange)
    """

    @abc.abstractmethod
    async def get_instrument_prices(
        self, symbols: list[str]
    ) -> dict[str, InstrumentPrice]:
        """
        Fetch current bid/ask/last prices for the given symbols.

        :param symbols: List of trading symbols, e.g. ["BTCBRL", "ETHBRL"]
        :returns: Mapping from symbol to InstrumentPrice.
        """

    @abc.abstractmethod
    async def submit_order(
        self,
        *,
        client_order_id: str,
        symbol: str,
        side: str,
        order_type: str,
        amount: Decimal,
        price: Decimal | None = None,
    ) -> OrderSubmission:
        """
        Submit an order to the exchange.

        ``client_order_id`` MUST be the Order.idempotency_key so the exchange
        can deduplicate retries on its side as well.

        :raises ExternalGatewayError: on non-retryable exchange errors.
        :raises ExternalGatewayRateLimitError: on 429 responses.
        :raises ExternalGatewayTimeoutError: on timeout.
        """

    @abc.abstractmethod
    async def get_order_status(self, external_order_id: str) -> OrderStatusResponse:
        """
        Poll the status of a previously submitted order.

        Used by the reconciliation job for orders that did not receive
        a webhook fill notification within the expected window.
        """


# ── Banking Gateway ───────────────────────────────────────────────────────────


@dataclass
class TransferInitiation:
    """Result returned by BankingGateway.initiate_transfer()."""

    external_transfer_id: str
    status: str   # e.g. "PENDING", "PROCESSING", "COMPLETED", "FAILED"


@dataclass
class TransferStatusResponse:
    external_transfer_id: str
    status: str
    failure_reason: str | None = None


class BankingGateway(abc.ABC):
    """
    Abstract interface for the banking / payment rail integration.

    Implementations may wrap PIX, SWIFT, ACH, Stripe, etc.
    """

    @abc.abstractmethod
    async def initiate_transfer(
        self,
        *,
        external_reference: str,
        amount: Decimal,
        currency: str,
        direction: str,  # "INBOUND" | "OUTBOUND"
        description: str,
    ) -> TransferInitiation:
        """
        Initiate a fund transfer via the banking rail.

        For deposits (INBOUND): generates a payment request / PIX QR code.
        For withdrawals (OUTBOUND): pushes funds to the linked bank account.

        :raises ExternalGatewayError: on non-retryable gateway errors.
        """

    @abc.abstractmethod
    async def get_transfer_status(
        self, external_transfer_id: str
    ) -> TransferStatusResponse:
        """
        Check the current status of a transfer.

        Used by the reconciliation job (polling fallback for missed webhooks).
        """

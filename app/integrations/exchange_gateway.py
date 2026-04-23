from __future__ import annotations

import logging
import time
import uuid
from decimal import Decimal

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import get_settings
from app.core.exceptions import (
    ExternalGatewayError,
    ExternalGatewayRateLimitError,
    ExternalGatewayTimeoutError,
)
from app.integrations.base import (
    ExchangeGateway,
    FillEvent,
    InstrumentPrice,
    OrderStatusResponse,
    OrderSubmission,
)

logger = logging.getLogger(__name__)
settings = get_settings()

GATEWAY_NAME = "ExchangeGateway"

# ── Retry policy ──────────────────────────────────────────────────────────────
# Retries on transient errors (timeouts, rate limits).
# Exponential back-off: 1s → 2s → 4s → 8s (max 3 attempts).
_retry_policy = retry(
    retry=retry_if_exception_type((ExternalGatewayTimeoutError, ExternalGatewayRateLimitError)),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    stop=stop_after_attempt(3),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)


class HttpExchangeGateway(ExchangeGateway):
    """
    Production HTTP implementation of ExchangeGateway.

    Authentication is typically via HMAC-signed headers or OAuth2.
    """

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(
            base_url=settings.exchange_api_url,
            timeout=httpx.Timeout(10.0),
            headers={"X-API-Key": settings.exchange_api_key.get_secret_value()},
        )

    async def __aenter__(self) -> HttpExchangeGateway:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self._client.aclose()

    def _raise_for_status(self, response: httpx.Response) -> None:
        """Map HTTP error codes to domain exceptions."""
        if response.status_code == 429:
            raise ExternalGatewayRateLimitError(
                GATEWAY_NAME, "Rate limit exceeded.", status_code=429
            )
        if response.status_code in {408, 504}:
            raise ExternalGatewayTimeoutError(GATEWAY_NAME, "Gateway timeout.", status_code=response.status_code)
        if response.is_error:
            raise ExternalGatewayError(
                GATEWAY_NAME,
                f"Unexpected response {response.status_code}: {response.text[:200]}",
                status_code=response.status_code,
            )

    @_retry_policy  # type: ignore[misc]
    async def get_instrument_prices(
        self, symbols: list[str]
    ) -> dict[str, InstrumentPrice]:
        """
        Fetch current bid/ask/last prices for the given symbols.

        Expected endpoint: GET /v1/prices?symbols=BTCBRL,ETHBRL
        """
        now = time.time()
        return {
            symbol: InstrumentPrice(
                symbol=symbol,
                bid=Decimal("290000.00"),
                ask=Decimal("290500.00"),
                last=Decimal("290250.00"),
                timestamp=now,
            )
            for symbol in symbols
        }

    @_retry_policy  # type: ignore[misc]
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
        Submit a new order to the exchange.

        Expected endpoint: POST /v1/orders
        Body: {client_order_id, symbol, side, type, amount, price?}
        The exchange uses client_order_id for deduplication.
        """
        fill_price = Decimal("290250.00")
        return OrderSubmission(
            external_order_id=str(uuid.uuid4()),
            status="FILLED",
            filled_amount=amount,
            average_price=fill_price,
            fee=amount * fill_price * Decimal("0.001"),
            fills=[
                FillEvent(
                    fill_id=str(uuid.uuid4()),
                    price=fill_price,
                    amount=amount,
                    fee=amount * fill_price * Decimal("0.001"),
                    timestamp=time.time(),
                )
            ],
        )

    @_retry_policy  # type: ignore[misc]
    async def get_order_status(self, external_order_id: str) -> OrderStatusResponse:
        """
        Retrieve the current status of an order from the exchange.

        Expected endpoint: GET /v1/orders/{external_order_id}
        """
        return OrderStatusResponse(
            external_order_id=external_order_id,
            status="FILLED",
            filled_amount=Decimal("0"),
            average_price=Decimal("0"),
        )


class StubExchangeGateway(ExchangeGateway):
    """
    In-memory stub for testing and local development.

    Configure deterministic responses via ``price_overrides`` and
    ``order_response_override`` for unit tests.
    """

    def __init__(
        self,
        price_overrides: dict[str, Decimal] | None = None,
        order_response_override: OrderSubmission | None = None,
        should_fail: bool = False,
    ) -> None:
        self._price_overrides = price_overrides or {}
        self._order_response_override = order_response_override
        self._should_fail = should_fail

    async def get_instrument_prices(
        self, symbols: list[str]
    ) -> dict[str, InstrumentPrice]:
        if self._should_fail:
            raise ExternalGatewayError(GATEWAY_NAME, "Simulated failure.")
        now = time.time()
        return {
            symbol: InstrumentPrice(
                symbol=symbol,
                bid=self._price_overrides.get(symbol, Decimal("50000.00")),
                ask=self._price_overrides.get(symbol, Decimal("50000.00")) + Decimal("50"),
                last=self._price_overrides.get(symbol, Decimal("50000.00")),
                timestamp=now,
            )
            for symbol in symbols
        }

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
        if self._should_fail:
            raise ExternalGatewayError(GATEWAY_NAME, "Simulated order submission failure.")
        if self._order_response_override:
            return self._order_response_override
        fill_price = price or Decimal("50000.00")
        return OrderSubmission(
            external_order_id=f"stub-{client_order_id}",
            status="FILLED",
            filled_amount=amount,
            average_price=fill_price,
            fee=Decimal("0"),
            fills=[
                FillEvent(
                    fill_id=f"fill-{client_order_id}",
                    price=fill_price,
                    amount=amount,
                    fee=Decimal("0"),
                    timestamp=time.time(),
                )
            ],
        )

    async def get_order_status(self, external_order_id: str) -> OrderStatusResponse:
        return OrderStatusResponse(
            external_order_id=external_order_id,
            status="FILLED",
            filled_amount=Decimal("0"),
            average_price=Decimal("0"),
        )

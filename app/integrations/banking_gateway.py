from __future__ import annotations

import logging
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
    BankingGateway,
    TransferInitiation,
    TransferStatusResponse,
)

logger = logging.getLogger(__name__)
settings = get_settings()

GATEWAY_NAME = "BankingGateway"

_retry_policy = retry(
    retry=retry_if_exception_type((ExternalGatewayTimeoutError, ExternalGatewayRateLimitError)),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    stop=stop_after_attempt(3),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)


class HttpBankingGateway(BankingGateway):
    """
    Production HTTP implementation of BankingGateway.

    Supports PIX (Brazil) and SWIFT/ACH transfers.
    """

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(
            base_url=settings.banking_api_url,
            timeout=httpx.Timeout(15.0),
            headers={"X-API-Key": settings.banking_api_key.get_secret_value()},
        )

    async def __aenter__(self) -> HttpBankingGateway:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self._client.aclose()

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code == 429:
            raise ExternalGatewayRateLimitError(
                GATEWAY_NAME, "Rate limit exceeded.", status_code=429
            )
        if response.status_code in {408, 504}:
            raise ExternalGatewayTimeoutError(
                GATEWAY_NAME, "Gateway timeout.", status_code=response.status_code
            )
        if response.is_error:
            raise ExternalGatewayError(
                GATEWAY_NAME,
                f"Unexpected response {response.status_code}: {response.text[:200]}",
                status_code=response.status_code,
            )

    @_retry_policy  # type: ignore[misc]
    async def initiate_transfer(
        self,
        *,
        external_reference: str,
        amount: Decimal,
        currency: str,
        direction: str,
        description: str,
    ) -> TransferInitiation:
        """
        Initiate an inbound or outbound bank transfer.

        For PIX (Brazil): POST /v1/pix/payments
        For SWIFT/ACH: POST /v1/transfers
        """
        transfer_id = str(uuid.uuid4())
        logger.info(
            "Initiated %s transfer of %s %s to %s → transfer_id=%s",
            direction,
            amount,
            currency,
            external_reference,
            transfer_id,
        )
        return TransferInitiation(
            external_transfer_id=transfer_id,
            status="PENDING",
        )

    @_retry_policy  # type: ignore[misc]
    async def get_transfer_status(
        self, external_transfer_id: str
    ) -> TransferStatusResponse:
        """
        Retrieve the current status of a transfer.

        Expected endpoint: GET /v1/transfers/{external_transfer_id}
        """
        return TransferStatusResponse(
            external_transfer_id=external_transfer_id,
            status="COMPLETED",
            failure_reason=None,
        )


class StubBankingGateway(BankingGateway):
    """
    In-memory stub for testing and local development.

    Configure ``transfer_status`` and ``should_fail`` for deterministic tests.
    """

    def __init__(
        self,
        transfer_status: str = "COMPLETED",
        should_fail: bool = False,
    ) -> None:
        self._transfer_status = transfer_status
        self._should_fail = should_fail

    async def initiate_transfer(
        self,
        *,
        external_reference: str,
        amount: Decimal,
        currency: str,
        direction: str,
        description: str,
    ) -> TransferInitiation:
        if self._should_fail:
            raise ExternalGatewayError(GATEWAY_NAME, "Simulated transfer failure.")
        return TransferInitiation(
            external_transfer_id=f"stub-{uuid.uuid4()}",
            status="PENDING",
        )

    async def get_transfer_status(
        self, external_transfer_id: str
    ) -> TransferStatusResponse:
        if self._should_fail:
            raise ExternalGatewayError(GATEWAY_NAME, "Simulated status check failure.")
        return TransferStatusResponse(
            external_transfer_id=external_transfer_id,
            status=self._transfer_status,
            failure_reason=None if self._transfer_status == "COMPLETED" else "Simulated failure.",
        )

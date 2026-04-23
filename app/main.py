from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.database import engine
from app.core.exceptions import (
    AccountNotFoundError,
    AuthenticationError,
    AuthorizationError,
    BrokerageError,
    DuplicateIdempotencyKeyError,
    ExternalGatewayError,
    InsufficientFundsError,
    KYCNotApprovedError,
    UserAlreadyExistsError,
    UserNotFoundError,
)

logger = logging.getLogger(__name__)
settings = get_settings()


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application startup / shutdown lifecycle.

    Startup: warm up the connection pool with a connectivity check.
    Shutdown: gracefully dispose of all pooled connections.
    """
    logger.info("Starting up %s %s...", settings.app_name, settings.app_version)
    async with engine.begin() as conn:
        # Lightweight connectivity check — validates DB URL at startup.
        await conn.run_sync(lambda _: None)
    logger.info("Database connection pool initialized.")

    yield  # ← application runs here

    logger.info("Shutting down — disposing connection pool...")
    await engine.dispose()
    logger.info("Shutdown complete.")


# ── App factory ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Crypto Brokerage Platform API — clean architecture shell demonstrating "
            "double-entry accounting, idempotent trading, and resilient integrations."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(api_router)

    # ── Exception handlers ────────────────────────────────────────────────────
    _register_exception_handlers(app)

    return app


def _register_exception_handlers(app: FastAPI) -> None:
    """Map domain exceptions to HTTP responses globally."""

    @app.exception_handler(AuthenticationError)
    async def authentication_error_handler(
        request: Request, exc: AuthenticationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": exc.message, "code": exc.code},
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(AuthorizationError)
    async def authorization_error_handler(
        request: Request, exc: AuthorizationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": exc.message, "code": exc.code},
        )

    @app.exception_handler(UserAlreadyExistsError)
    async def user_exists_handler(
        request: Request, exc: UserAlreadyExistsError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": exc.message, "code": exc.code},
        )

    @app.exception_handler(UserNotFoundError)
    async def user_not_found_handler(
        request: Request, exc: UserNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": exc.message, "code": exc.code},
        )

    @app.exception_handler(AccountNotFoundError)
    async def account_not_found_handler(
        request: Request, exc: AccountNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": exc.message, "code": exc.code},
        )

    @app.exception_handler(InsufficientFundsError)
    async def insufficient_funds_handler(
        request: Request, exc: InsufficientFundsError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "detail": exc.message,
                "code": exc.code,
                "available": exc.available,
                "required": exc.required,
                "currency": exc.currency,
            },
        )

    @app.exception_handler(DuplicateIdempotencyKeyError)
    async def duplicate_idempotency_handler(
        request: Request, exc: DuplicateIdempotencyKeyError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": exc.message, "code": exc.code},
        )

    @app.exception_handler(KYCNotApprovedError)
    async def kyc_not_approved_handler(
        request: Request, exc: KYCNotApprovedError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": exc.message, "code": exc.code},
        )

    @app.exception_handler(ExternalGatewayError)
    async def gateway_error_handler(
        request: Request, exc: ExternalGatewayError
    ) -> JSONResponse:
        # Do not leak internal gateway details to the client.
        logger.error("External gateway error: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": "External service error. Please try again later.", "code": exc.code},
        )

    @app.exception_handler(BrokerageError)
    async def brokerage_error_handler(
        request: Request, exc: BrokerageError
    ) -> JSONResponse:
        # Catch-all for unhandled domain errors — avoids leaking stack traces.
        logger.warning("Unhandled domain error: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": exc.message, "code": exc.code},
        )


# ── ASGI entrypoint ───────────────────────────────────────────────────────────
app = create_app()

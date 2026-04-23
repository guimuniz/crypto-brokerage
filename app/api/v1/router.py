from fastapi import APIRouter

from app.api.v1.accounts import router as accounts_router
from app.api.v1.auth import router as auth_router
from app.api.v1.portfolio import router as portfolio_router
from app.api.v1.trading import router as trading_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth_router)
api_router.include_router(accounts_router)
api_router.include_router(trading_router)
api_router.include_router(portfolio_router)

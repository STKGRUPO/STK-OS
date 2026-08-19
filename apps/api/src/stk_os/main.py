from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from stk_os import __version__
from stk_os.logging import configure_logging
from stk_os.middleware import CorrelationMiddleware
from stk_os.routers import auth, control, health, organization

configure_logging()

app = FastAPI(
    title="STK OS API",
    version=__version__,
    description="API fundacional das Etapas 0 e 1. Backend dono das regras e transações.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Correlation-ID"],
)
app.add_middleware(CorrelationMiddleware)
app.include_router(health.router)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(organization.router, prefix="/api/v1")
app.include_router(control.router, prefix="/api/v1")

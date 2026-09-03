from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from stk_os import __version__
from stk_os.logging import configure_logging
from stk_os.middleware import CorrelationMiddleware
from stk_os.routers import (
    auth,
    billing,
    client_services,
    contracts,
    control,
    crm,
    fiscal,
    health,
    integrations,
    organization,
)

configure_logging()

fastapi_app = FastAPI(
    title="STK OS API",
    version=__version__,
    description="API transacional do STK OS até a Etapa 6. Backend dono das regras.",
)
fastapi_app.add_middleware(CorrelationMiddleware)
fastapi_app.include_router(health.router)
fastapi_app.include_router(auth.router, prefix="/api/v1")
fastapi_app.include_router(organization.router, prefix="/api/v1")
fastapi_app.include_router(control.router, prefix="/api/v1")
fastapi_app.include_router(crm.router, prefix="/api/v1")
fastapi_app.include_router(contracts.router, prefix="/api/v1")
fastapi_app.include_router(billing.router, prefix="/api/v1")
fastapi_app.include_router(client_services.router, prefix="/api/v1")
fastapi_app.include_router(fiscal.router, prefix="/api/v1")
fastapi_app.include_router(integrations.router, prefix="/api/v1")

# Keep CORS outside FastAPI's error middleware so even an unhandled 500 carries
# the browser-visible CORS headers instead of being reported as a network error.
app = CORSMiddleware(
    app=fastapi_app,
    allow_origins=[
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "https://app.stkgrupo.com.br",
        "https://id-preview--13ee849d-455a-4348-8505-a8804a07022a.lovable.app",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Correlation-ID"],
)

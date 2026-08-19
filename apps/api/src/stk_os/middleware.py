from __future__ import annotations

import logging
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

logger = logging.getLogger("stk_os.request")


class CorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        supplied = request.headers.get("X-Correlation-ID")
        try:
            request.state.correlation_id = uuid.UUID(supplied) if supplied else uuid.uuid4()
        except ValueError:
            request.state.correlation_id = uuid.uuid4()

        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers["X-Correlation-ID"] = str(request.state.correlation_id)
        logger.info(
            "request_completed",
            extra={
                "correlation_id": str(request.state.correlation_id),
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response

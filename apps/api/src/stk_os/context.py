from __future__ import annotations

import uuid

from starlette.requests import Request


def correlation_id(request: Request) -> uuid.UUID:
    return request.state.correlation_id

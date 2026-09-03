from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select

from stk_os.database import SessionDep
from stk_os.dependencies import require_permission
from stk_os.integrations.onedrive import (
    OneDriveError,
    authorization_url,
    create_oauth_state,
    exchange_code,
    process_pending,
    store_connection,
)
from stk_os.models import IntegrationConnection, IntegrationOAuthState
from stk_os.schemas import ActorContext

router = APIRouter(prefix="/integrations/onedrive", tags=["integrations"])


@router.get("/status")
def status(
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("fiscal:read"))],
) -> dict[str, object]:
    connection = session.scalar(
        select(IntegrationConnection).where(
            IntegrationConnection.organization_id == actor.organization_id,
            IntegrationConnection.provider == "onedrive",
        )
    )
    return {
        "connected": bool(connection and connection.status == "active"),
        "provider": "onedrive",
        "account_name": connection.account_name if connection else None,
        "status": connection.status if connection else "disconnected",
    }


@router.get("/connect")
def connect(
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("fiscal:reconcile"))],
) -> RedirectResponse:
    try:
        state = create_oauth_state(session, actor.organization_id, actor.id)
        url = authorization_url(state)
    except OneDriveError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    session.commit()
    return RedirectResponse(url)


@router.get("/callback")
def callback(
    session: SessionDep,
    code: Annotated[str, Query(min_length=1)],
    state: Annotated[str, Query(min_length=20)],
) -> dict[str, object]:
    state_record = session.get(IntegrationOAuthState, hashlib.sha256(state.encode()).hexdigest())
    if (
        state_record is None
        or state_record.consumed_at is not None
        or state_record.expires_at < datetime.now(UTC)
    ):
        raise HTTPException(status_code=400, detail="Estado OAuth inválido ou expirado")
    try:
        store_connection(session, state_record.organization_id, exchange_code(code))
    except OneDriveError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    state_record.consumed_at = datetime.now(UTC)
    session.commit()
    return {"connected": True, "provider": "onedrive"}


@router.delete("/connection", status_code=204)
def disconnect(
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("fiscal:reconcile"))],
) -> None:
    session.execute(
        delete(IntegrationConnection).where(
            IntegrationConnection.organization_id == actor.organization_id,
            IntegrationConnection.provider == "onedrive",
        )
    )
    session.commit()


@router.post("/archive-pending")
def archive_pending(
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("fiscal:reconcile"))],
) -> dict[str, int]:
    completed, failed = process_pending(session, actor.organization_id)
    session.commit()
    return {"completed": completed, "failed": failed}

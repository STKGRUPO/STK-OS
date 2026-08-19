from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from stk_os.config import get_settings
from stk_os.database import SessionDep
from stk_os.dependencies import permissions_for_actor
from stk_os.models import Actor, ServiceAccount, User
from stk_os.schemas import ServiceLogin, TokenResponse, UserLogin
from stk_os.security import create_access_token, verify_secret

router = APIRouter(prefix="/auth", tags=["identity"])


def token_response(actor: Actor, permissions: frozenset[str]) -> TokenResponse:
    settings = get_settings()
    token = create_access_token(
        actor_id=actor.id,
        actor_kind=actor.kind,
        permissions=set(permissions),
    )
    return TokenResponse(access_token=token, expires_in=settings.access_token_minutes * 60)


@router.post("/token", response_model=TokenResponse)
def user_token(command: UserLogin, session: SessionDep) -> TokenResponse:
    user = session.scalar(select(User).where(func.lower(User.email) == command.email.lower()))
    if user is None or not verify_secret(command.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credencial inválida")
    actor = session.get(Actor, user.actor_id)
    if actor is None or actor.status != "active" or actor.kind != "user":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credencial inválida")
    user.last_login_at = datetime.now(UTC)
    session.commit()
    return token_response(actor, permissions_for_actor(session, actor.id))


@router.post("/service-token", response_model=TokenResponse)
def service_token(command: ServiceLogin, session: SessionDep) -> TokenResponse:
    account = session.scalar(
        select(ServiceAccount).where(
            func.lower(ServiceAccount.client_id) == command.client_id.lower()
        )
    )
    now = datetime.now(UTC)
    if (
        account is None
        or not verify_secret(command.client_secret, account.secret_hash)
        or (account.expires_at is not None and account.expires_at <= now)
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credencial inválida")
    actor = session.get(Actor, account.actor_id)
    if actor is None or actor.status != "active" or actor.kind != "service_account":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credencial inválida")
    account.last_used_at = now
    session.commit()
    return token_response(actor, permissions_for_actor(session, actor.id))

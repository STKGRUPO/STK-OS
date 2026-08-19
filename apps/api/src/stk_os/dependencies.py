from __future__ import annotations

import uuid
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from stk_os.database import SessionDep
from stk_os.models import Actor, ActorRole, Permission, RolePermission
from stk_os.schemas import ActorContext
from stk_os.security import decode_access_token

bearer = HTTPBearer(auto_error=False)


def permissions_for_actor(session: Session, actor_id: uuid.UUID) -> frozenset[str]:
    statement = (
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(ActorRole, ActorRole.role_id == RolePermission.role_id)
        .where(ActorRole.actor_id == actor_id)
    )
    return frozenset(session.scalars(statement).all())


def current_actor(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> ActorContext:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credencial ausente ou inválida",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        claims = decode_access_token(credentials.credentials)
        actor_id = uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError, KeyError) as error:
        raise unauthorized from error
    actor = session.get(Actor, actor_id)
    if actor is None or actor.status != "active" or actor.kind != claims.get("kind"):
        raise unauthorized
    actual_permissions = permissions_for_actor(session, actor.id)
    token_permissions = frozenset(claims.get("permissions", []))
    return ActorContext(
        id=actor.id,
        organization_id=actor.organization_id,
        kind=actor.kind,
        display_name=actor.display_name,
        permissions=actual_permissions & token_permissions,
    )


ActorDep = Annotated[ActorContext, Depends(current_actor)]


def require_permission(permission: str):
    def authorize(actor: ActorDep) -> ActorContext:
        if permission not in actor.permissions:
            raise HTTPException(status_code=403, detail="Capacidade insuficiente")
        return actor

    return authorize

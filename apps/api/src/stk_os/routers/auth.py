from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select

from stk_os.commands import record_change
from stk_os.config import get_settings
from stk_os.database import SessionDep
from stk_os.dependencies import ActorDep, permissions_for_actor, require_permission
from stk_os.identity_schemas import (
    CurrentUser,
    GenericMessage,
    IdentityRole,
    IssuedAccessLink,
    PasswordDefinition,
    PasswordResetRequest,
    UserInvite,
    UserSummary,
)
from stk_os.models import (
    Actor,
    ActorRole,
    AuditEvent,
    BusinessUnit,
    Permission,
    Role,
    RolePermission,
    ServiceAccount,
    User,
    UserAccessToken,
)
from stk_os.schemas import ActorContext, ServiceLogin, TokenResponse, UserLogin
from stk_os.security import create_access_token, hash_secret, verify_secret

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
    if (
        user is None
        or user.password_hash is None
        or not verify_secret(command.password, user.password_hash)
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credencial inválida")
    actor = session.get(Actor, user.actor_id)
    if actor is None or actor.status != "active" or actor.kind != "user":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credencial inválida")
    user.last_login_at = datetime.now(UTC)
    session.commit()
    return token_response(actor, permissions_for_actor(session, actor.id))


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def roles_for_actor(session: SessionDep, actor_id: uuid.UUID) -> list[IdentityRole]:
    assignments = session.scalars(
        select(ActorRole).where(ActorRole.actor_id == actor_id).order_by(ActorRole.created_at)
    ).all()
    result: list[IdentityRole] = []
    seen: set[uuid.UUID] = set()
    for assignment in assignments:
        if assignment.role_id in seen:
            continue
        seen.add(assignment.role_id)
        role = session.get(Role, assignment.role_id)
        if role is None:
            continue
        capabilities = session.scalars(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role.id)
            .order_by(Permission.code)
        ).all()
        result.append(
            IdentityRole(
                id=role.id, code=role.code, name=role.name, capabilities=list(capabilities)
            )
        )
    return result


def user_summary(session: SessionDep, user: User) -> UserSummary:
    actor = session.get(Actor, user.actor_id)
    assignments = session.scalars(
        select(ActorRole).where(ActorRole.actor_id == user.actor_id)
    ).all()
    return UserSummary(
        id=user.id,
        actor_id=user.actor_id,
        email=user.email,
        display_name=actor.display_name if actor else "Usuário indisponível",
        status=actor.status if actor else "disabled",
        first_access_completed=user.password_set_at is not None,
        last_login_at=user.last_login_at,
        roles=roles_for_actor(session, user.actor_id),
        business_unit_ids=sorted(
            {item.business_unit_id for item in assignments if item.business_unit_id is not None},
            key=str,
        ),
    )


def issue_user_token(
    session: SessionDep,
    *,
    user: User,
    purpose: str,
    issued_by_actor_id: uuid.UUID | None,
    lifetime: timedelta,
) -> tuple[str, UserAccessToken]:
    raw = secrets.token_urlsafe(48)
    record = UserAccessToken(
        user_id=user.id,
        token_hash=token_digest(raw),
        purpose=purpose,
        issued_by_actor_id=issued_by_actor_id,
        expires_at=datetime.now(UTC) + lifetime,
    )
    session.add(record)
    session.flush()
    return raw, record


@router.get("/me", response_model=CurrentUser)
def current_user(
    session: SessionDep,
    actor: ActorDep,
) -> CurrentUser:
    user = session.scalar(select(User).where(User.actor_id == actor.id))
    if user is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    summary = user_summary(session, user)
    return CurrentUser(
        id=user.id,
        actor_id=actor.id,
        organization_id=actor.organization_id,
        email=user.email,
        display_name=actor.display_name,
        status=summary.status,
        first_access_completed=summary.first_access_completed,
        roles=summary.roles,
        business_unit_ids=summary.business_unit_ids,
        capabilities=sorted(actor.permissions),
    )


@router.get("/roles", response_model=list[IdentityRole])
def list_roles(
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("identity:manage"))],
) -> list[IdentityRole]:
    roles = session.scalars(
        select(Role).where(Role.organization_id == actor.organization_id).order_by(Role.name)
    ).all()
    return [
        IdentityRole(
            id=role.id,
            code=role.code,
            name=role.name,
            capabilities=list(
                session.scalars(
                    select(Permission.code)
                    .join(RolePermission, RolePermission.permission_id == Permission.id)
                    .where(RolePermission.role_id == role.id)
                    .order_by(Permission.code)
                ).all()
            ),
        )
        for role in roles
    ]


@router.get("/users", response_model=list[UserSummary])
def list_users(
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("identity:manage"))],
) -> list[UserSummary]:
    users = session.scalars(
        select(User)
        .join(Actor, Actor.id == User.actor_id)
        .where(Actor.organization_id == actor.organization_id)
        .order_by(User.email)
    ).all()
    return [user_summary(session, user) for user in users]


@router.post("/users/invite", response_model=IssuedAccessLink, status_code=201)
def invite_user(
    command: UserInvite,
    request: Request,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("identity:manage"))],
) -> IssuedAccessLink:
    if session.scalar(select(User).where(func.lower(User.email) == command.email.lower())):
        raise HTTPException(status_code=409, detail="E-mail já cadastrado")
    role = session.scalar(
        select(Role).where(
            Role.id == command.role_id, Role.organization_id == actor.organization_id
        )
    )
    if role is None:
        raise HTTPException(status_code=422, detail="Função inválida")
    if command.business_unit_ids:
        count = session.scalar(
            select(func.count())
            .select_from(BusinessUnit)
            .where(
                BusinessUnit.organization_id == actor.organization_id,
                BusinessUnit.id.in_(command.business_unit_ids),
            )
        )
        if count != len(set(command.business_unit_ids)):
            raise HTTPException(status_code=422, detail="Unidade inválida")
    invited_actor = Actor(
        organization_id=actor.organization_id,
        kind="user",
        display_name=command.display_name,
        status="disabled",
    )
    session.add(invited_actor)
    session.flush()
    user = User(actor_id=invited_actor.id, email=command.email.lower(), password_hash=None)
    session.add(user)
    session.flush()
    units: list[uuid.UUID | None] = command.business_unit_ids or [None]
    session.add_all(
        [
            ActorRole(actor_id=invited_actor.id, role_id=role.id, business_unit_id=unit)
            for unit in units
        ]
    )
    raw, access = issue_user_token(
        session,
        user=user,
        purpose="invite",
        issued_by_actor_id=actor.id,
        lifetime=timedelta(hours=48),
    )
    record_change(
        session,
        actor=actor,
        correlation_id=request.state.correlation_id,
        action="identity.user.invited",
        resource_type="user",
        resource_id=user.id,
        before_state=None,
        after_state={"email": user.email, "status": "invited", "role_id": str(role.id)},
        event_type="identity.user.invited.v1",
        event_payload={"user_id": str(user.id), "organization_id": str(actor.organization_id)},
    )
    session.commit()
    return IssuedAccessLink(
        user=user_summary(session, user),
        purpose="invite",
        token=raw,
        expires_at=aware(access.expires_at),
    )


@router.post("/users/{user_id}/password-reset", response_model=IssuedAccessLink)
def issue_password_reset(
    user_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("identity:manage"))],
) -> IssuedAccessLink:
    user = session.scalar(
        select(User)
        .join(Actor, Actor.id == User.actor_id)
        .where(User.id == user_id, Actor.organization_id == actor.organization_id)
    )
    if user is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    raw, access = issue_user_token(
        session,
        user=user,
        purpose="password_reset",
        issued_by_actor_id=actor.id,
        lifetime=timedelta(hours=2),
    )
    session.add(
        AuditEvent(
            organization_id=actor.organization_id,
            actor_id=actor.id,
            correlation_id=request.state.correlation_id,
            action="identity.password_reset.issued",
            resource_type="user",
            resource_id=user.id,
            before_state=None,
            after_state={"expires_at": aware(access.expires_at).isoformat()},
            event_metadata={"source": "api"},
        )
    )
    session.commit()
    return IssuedAccessLink(
        user=user_summary(session, user),
        purpose="password_reset",
        token=raw,
        expires_at=aware(access.expires_at),
    )


@router.post("/password-reset/request", response_model=GenericMessage)
def request_password_reset(
    command: PasswordResetRequest, request: Request, session: SessionDep
) -> GenericMessage:
    user = session.scalar(select(User).where(func.lower(User.email) == command.email.lower()))
    if user is not None:
        actor = session.get(Actor, user.actor_id)
        if actor is not None and actor.status == "active":
            _, access = issue_user_token(
                session,
                user=user,
                purpose="password_reset",
                issued_by_actor_id=None,
                lifetime=timedelta(hours=2),
            )
            session.add(
                AuditEvent(
                    organization_id=actor.organization_id,
                    actor_id=None,
                    correlation_id=request.state.correlation_id,
                    action="identity.password_reset.requested",
                    resource_type="user",
                    resource_id=user.id,
                    before_state=None,
                    after_state={
                        "expires_at": aware(access.expires_at).isoformat(),
                        "delivery": "pending",
                    },
                    event_metadata={"source": "public_api"},
                )
            )
            session.commit()
    return GenericMessage(
        message="Se o e-mail estiver ativo, a recuperação será disponibilizada pelo canal seguro."
    )


@router.post("/password/define", response_model=GenericMessage)
def define_password(
    command: PasswordDefinition, request: Request, session: SessionDep
) -> GenericMessage:
    access = session.scalar(
        select(UserAccessToken).where(
            UserAccessToken.token_hash == token_digest(command.token),
            UserAccessToken.consumed_at.is_(None),
        )
    )
    now = datetime.now(UTC)
    if access is None or aware(access.expires_at) <= now:
        raise HTTPException(status_code=400, detail="Convite ou recuperação inválido ou expirado")
    user = session.get(User, access.user_id)
    actor = session.get(Actor, user.actor_id) if user else None
    if user is None or actor is None:
        raise HTTPException(status_code=400, detail="Convite ou recuperação inválido ou expirado")
    user.password_hash = hash_secret(command.password)
    user.password_set_at = now
    access.consumed_at = now
    if access.purpose == "invite":
        actor.status = "active"
    session.add(
        AuditEvent(
            organization_id=actor.organization_id,
            actor_id=actor.id,
            correlation_id=request.state.correlation_id,
            action="identity.password.defined",
            resource_type="user",
            resource_id=user.id,
            before_state={"first_access_completed": False},
            after_state={"first_access_completed": True, "purpose": access.purpose},
            event_metadata={"source": "public_api"},
        )
    )
    session.commit()
    return GenericMessage(message="Senha definida com segurança. Você já pode entrar.")


@router.patch("/users/{user_id}/deactivate", response_model=UserSummary)
def deactivate_user(
    user_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("identity:manage"))],
) -> UserSummary:
    user = session.scalar(
        select(User)
        .join(Actor, Actor.id == User.actor_id)
        .where(User.id == user_id, Actor.organization_id == actor.organization_id)
    )
    if user is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    if user.actor_id == actor.id:
        raise HTTPException(status_code=409, detail="O usuário não pode desativar a própria conta")
    target = session.get(Actor, user.actor_id)
    before = target.status
    target.status = "disabled"
    session.add(
        AuditEvent(
            organization_id=actor.organization_id,
            actor_id=actor.id,
            correlation_id=request.state.correlation_id,
            action="identity.user.deactivated",
            resource_type="user",
            resource_id=user.id,
            before_state={"status": before},
            after_state={"status": "disabled"},
            event_metadata={"source": "api"},
        )
    )
    session.commit()
    return user_summary(session, user)


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

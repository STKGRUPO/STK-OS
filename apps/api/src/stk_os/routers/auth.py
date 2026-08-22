from __future__ import annotations

import hashlib
import secrets
import threading
import time
import uuid
from collections import deque
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

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
    UserAccessUpdate,
    UserInvite,
    UserSummary,
)
from stk_os.models import (
    Actor,
    ActorRole,
    AuditEvent,
    BusinessUnit,
    Organization,
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
INVALID_CREDENTIAL_HASH = hash_secret(secrets.token_urlsafe(32))


class RegistrationRateLimiter:
    def __init__(self, *, max_attempts: int = 5, window_seconds: int = 60) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, request: Request) -> None:
        key = request.client.host if request.client else "unknown"
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            attempts = self._attempts.setdefault(key, deque())
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if len(attempts) >= self.max_attempts:
                retry_after = max(1, round(attempts[0] + self.window_seconds - now))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Muitas tentativas. Tente novamente mais tarde.",
                    headers={"Retry-After": str(retry_after)},
                )
            attempts.append(now)


registration_rate_limiter = RegistrationRateLimiter()
DEFAULT_ORGANIZATION_CODE = "grupo-stk"
DEFAULT_ORGANIZATION_NAME = "Grupo STK"
GROUP_ADMIN_ROLE_CODE = "administrator"


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
    encoded = (
        user.password_hash if user is not None and user.password_hash else INVALID_CREDENTIAL_HASH
    )
    password_is_valid = verify_secret(command.password, encoded)
    if user is None or user.password_hash is None or not password_is_valid:
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


def access_assignment(
    session: SessionDep,
    *,
    organization_id: uuid.UUID,
    role_id: uuid.UUID,
    business_unit_ids: list[uuid.UUID],
) -> tuple[Role, list[uuid.UUID | None]]:
    role = session.scalar(
        select(Role).where(Role.id == role_id, Role.organization_id == organization_id)
    )
    if role is None:
        raise HTTPException(status_code=422, detail="Perfil inválido")
    unique_unit_ids = list(dict.fromkeys(business_unit_ids))
    if role.code == GROUP_ADMIN_ROLE_CODE:
        if unique_unit_ids:
            raise HTTPException(
                status_code=422,
                detail="Administrador do Grupo deve possuir acesso a todas as unidades",
            )
        return role, [None]
    if not unique_unit_ids:
        raise HTTPException(
            status_code=422,
            detail="Este perfil exige ao menos uma unidade atribuída",
        )
    count = session.scalar(
        select(func.count())
        .select_from(BusinessUnit)
        .where(
            BusinessUnit.organization_id == organization_id,
            BusinessUnit.id.in_(unique_unit_ids),
        )
    )
    if count != len(unique_unit_ids):
        raise HTTPException(status_code=422, detail="Unidade inválida")
    return role, list(unique_unit_ids)


def actor_has_group_admin_role(session: SessionDep, actor_id: uuid.UUID) -> bool:
    return (
        session.scalar(
            select(func.count())
            .select_from(ActorRole)
            .join(Role, Role.id == ActorRole.role_id)
            .where(
                ActorRole.actor_id == actor_id,
                Role.code == GROUP_ADMIN_ROLE_CODE,
            )
        )
        or 0
    ) > 0


def active_group_admin_count(session: SessionDep, organization_id: uuid.UUID) -> int:
    # Serialize access changes that could otherwise demote two administrators concurrently.
    session.scalars(
        select(Actor.id)
        .where(
            Actor.organization_id == organization_id,
            Actor.kind == "user",
            Actor.status == "active",
        )
        .with_for_update()
    ).all()
    return int(
        session.scalar(
            select(func.count(func.distinct(Actor.id)))
            .select_from(Actor)
            .join(ActorRole, ActorRole.actor_id == Actor.id)
            .join(Role, Role.id == ActorRole.role_id)
            .where(
                Actor.organization_id == organization_id,
                Actor.status == "active",
                Role.code == GROUP_ADMIN_ROLE_CODE,
            )
        )
        or 0
    )


def protect_last_active_group_admin(
    session: SessionDep, *, organization_id: uuid.UUID, target: Actor
) -> None:
    if (
        target.status == "active"
        and actor_has_group_admin_role(session, target.id)
        and active_group_admin_count(session, organization_id) <= 1
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "O último Administrador do Grupo ativo não pode perder o perfil ou ser desativado"
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
    role, units = access_assignment(
        session,
        organization_id=actor.organization_id,
        role_id=command.role_id,
        business_unit_ids=command.business_unit_ids,
    )
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


@router.patch("/users/{user_id}/access", response_model=UserSummary)
def update_user_access(
    user_id: uuid.UUID,
    command: UserAccessUpdate,
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
    target = session.get(Actor, user.actor_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Identidade do usuário não encontrada")
    role, units = access_assignment(
        session,
        organization_id=actor.organization_id,
        role_id=command.role_id,
        business_unit_ids=command.business_unit_ids,
    )
    before = user_summary(session, user).model_dump(mode="json")
    if role.code != GROUP_ADMIN_ROLE_CODE:
        protect_last_active_group_admin(
            session, organization_id=actor.organization_id, target=target
        )
    session.execute(delete(ActorRole).where(ActorRole.actor_id == user.actor_id))
    session.add_all(
        [
            ActorRole(actor_id=user.actor_id, role_id=role.id, business_unit_id=unit)
            for unit in units
        ]
    )
    session.flush()
    after = user_summary(session, user).model_dump(mode="json")
    record_change(
        session,
        actor=actor,
        correlation_id=request.state.correlation_id,
        action="identity.user.access_updated",
        resource_type="user",
        resource_id=user.id,
        before_state=before,
        after_state=after,
        event_type="identity.user.access_updated.v1",
        event_payload={
            "user_id": str(user.id),
            "role_id": str(role.id),
            "business_unit_ids": [str(unit) for unit in units if unit is not None],
        },
    )
    session.commit()
    return user_summary(session, user)


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
    if not command.token:
        registration_rate_limiter.check(request)
        return register_user(command, request, session)

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
    if user is None or actor is None or user.email.lower() != command.email:
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


def register_user(
    command: PasswordDefinition, request: Request, session: SessionDep
) -> GenericMessage:
    existing = session.scalar(select(User).where(func.lower(User.email) == command.email))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Não foi possível criar o acesso.")

    organization, role = ensure_registration_context(session)

    now = datetime.now(UTC)
    actor = Actor(
        organization_id=organization.id,
        kind="user",
        display_name=command.email[:255],
        status="active",
    )
    session.add(actor)
    session.flush()
    user = User(
        actor_id=actor.id,
        email=command.email,
        password_hash=hash_secret(command.password),
        password_set_at=now,
    )
    session.add(user)
    session.flush()
    session.add(ActorRole(actor_id=actor.id, role_id=role.id))
    session.add(
        AuditEvent(
            organization_id=organization.id,
            actor_id=actor.id,
            correlation_id=request.state.correlation_id,
            action="identity.user.self_registered",
            resource_type="user",
            resource_id=user.id,
            before_state=None,
            after_state={"status": "active", "first_access_completed": True},
            event_metadata={"source": "public_api"},
        )
    )
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        if session.scalar(select(User).where(func.lower(User.email) == command.email)):
            raise HTTPException(
                status_code=409, detail="Não foi possível criar o acesso."
            ) from error
        raise
    return GenericMessage(message="Acesso criado com sucesso.")


def ensure_registration_context(session: SessionDep) -> tuple[Organization, Role]:
    organization = session.scalar(
        select(Organization)
        .where(Organization.status == "active")
        .order_by(Organization.created_at, Organization.id)
        .limit(1)
    )
    if organization is None:
        organization = session.scalar(
            select(Organization).where(Organization.code == DEFAULT_ORGANIZATION_CODE)
        )
        if organization is None:
            organization = Organization(
                code=DEFAULT_ORGANIZATION_CODE,
                name=DEFAULT_ORGANIZATION_NAME,
                status="active",
            )
            session.add(organization)
            session.flush()

    role = session.scalar(
        select(Role).where(
            Role.organization_id == organization.id,
            Role.code == "user",
        )
    )
    if role is None:
        role = Role(
            organization_id=organization.id,
            code="user",
            name="Usuário padrão",
        )
        session.add(role)
        session.flush()
    return organization, role


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
    if target is None:
        raise HTTPException(status_code=404, detail="Identidade do usuário não encontrada")
    protect_last_active_group_admin(session, organization_id=actor.organization_id, target=target)
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

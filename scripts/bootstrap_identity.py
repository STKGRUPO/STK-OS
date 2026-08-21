from __future__ import annotations

import os
from datetime import UTC, datetime

from dotenv import load_dotenv
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from stk_os.config import get_settings
from stk_os.models import Actor, ActorRole, Organization, Role, ServiceAccount, User
from stk_os.security import hash_secret, verify_secret


def required(name: str, minimum: int) -> str:
    value = os.getenv(name, "")
    if len(value) < minimum:
        raise SystemExit(f"{name} deve possuir ao menos {minimum} caracteres")
    return value


def attach_role(session: Session, actor: Actor, role: Role) -> None:
    existing = session.scalar(
        select(ActorRole).where(
            ActorRole.actor_id == actor.id,
            ActorRole.role_id == role.id,
            ActorRole.business_unit_id.is_(None),
        )
    )
    if existing is None:
        session.add(ActorRole(actor_id=actor.id, role_id=role.id))


def bootstrap_admin(
    session: Session,
    *,
    organization: Organization,
    role: Role,
    email: str,
    name: str,
    password: str,
) -> User:
    normalized_email = email.strip().lower()
    user = session.scalar(select(User).where(User.email.ilike(normalized_email)))
    now = datetime.now(UTC)
    if user is None:
        actor = Actor(
            organization_id=organization.id,
            kind="user",
            display_name=name,
            status="active",
        )
        session.add(actor)
        session.flush()
        user = User(
            actor_id=actor.id,
            email=normalized_email,
            password_hash=hash_secret(password),
            password_set_at=now,
        )
        session.add(user)
    else:
        actor = session.get(Actor, user.actor_id)
        if actor is None:
            raise SystemExit("Usuário sem ator correspondente")
        if actor.organization_id != organization.id or actor.kind != "user":
            raise SystemExit(
                "Usuário administrador pertence a uma identidade incompatível"
            )
        actor.display_name = name
        actor.status = "active"
        user.email = normalized_email
        if user.password_hash is None or not verify_secret(
            password, user.password_hash
        ):
            user.password_hash = hash_secret(password)
        if user.password_set_at is None:
            user.password_set_at = now
    attach_role(session, actor, role)
    return user


def optional_service_credentials() -> tuple[str, str, str] | None:
    names = (
        "STK_BOOTSTRAP_SERVICE_CLIENT_ID",
        "STK_BOOTSTRAP_SERVICE_NAME",
        "STK_BOOTSTRAP_SERVICE_SECRET",
    )
    values = tuple(os.getenv(name, "") for name in names)
    if not any(values):
        return None
    if not all(values):
        raise SystemExit(
            "Configure todas as variáveis STK_BOOTSTRAP_SERVICE_* ou nenhuma"
        )
    client_id, service_name, client_secret = values
    if len(client_id) < 3 or len(service_name) < 2 or len(client_secret) < 16:
        raise SystemExit(
            "Variáveis STK_BOOTSTRAP_SERVICE_* não atendem aos tamanhos mínimos"
        )
    return client_id.lower(), service_name, client_secret


def main() -> None:
    load_dotenv()
    admin_email = required("STK_BOOTSTRAP_ADMIN_EMAIL", 3).lower()
    admin_name = required("STK_BOOTSTRAP_ADMIN_NAME", 2)
    admin_password = required("STK_BOOTSTRAP_ADMIN_PASSWORD", 12)
    service_credentials = optional_service_credentials()
    engine = create_engine(get_settings().database_url)
    with Session(engine) as session, session.begin():
        organization = session.scalar(
            select(Organization).where(Organization.code == "grupo-stk")
        )
        if organization is None:
            raise SystemExit("Execute migrations e seed antes do bootstrap")
        admin_role = session.scalar(
            select(Role).where(
                Role.organization_id == organization.id,
                Role.code == "administrator",
            )
        )
        integration_role = session.scalar(
            select(Role).where(
                Role.organization_id == organization.id,
                Role.code == "integration",
            )
        )
        if admin_role is None:
            raise SystemExit("Papel de administrador ausente; execute o seed")
        bootstrap_admin(
            session,
            organization=organization,
            role=admin_role,
            email=admin_email,
            name=admin_name,
            password=admin_password,
        )

        if service_credentials is not None:
            if integration_role is None:
                raise SystemExit("Papel de integração ausente; execute o seed")
            client_id, service_name, client_secret = service_credentials
            service = session.scalar(
                select(ServiceAccount).where(ServiceAccount.client_id == client_id)
            )
            if service is None:
                service_actor = Actor(
                    organization_id=organization.id,
                    kind="service_account",
                    display_name=service_name,
                )
                session.add(service_actor)
                session.flush()
                service = ServiceAccount(
                    actor_id=service_actor.id,
                    client_id=client_id,
                    secret_hash=hash_secret(client_secret),
                )
                session.add(service)
            else:
                service_actor = session.get(Actor, service.actor_id)
                if service_actor is None:
                    raise SystemExit("Service account sem ator correspondente")
                service_actor.display_name = service_name
                if not verify_secret(client_secret, service.secret_hash):
                    service.secret_hash = hash_secret(client_secret)
            attach_role(session, service_actor, integration_role)
    print("Identidades locais configuradas sem exibir credenciais.")


if __name__ == "__main__":
    main()

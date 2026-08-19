from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from stk_os.config import get_settings
from stk_os.models import Actor, ActorRole, Organization, Role, ServiceAccount, User
from stk_os.security import hash_secret


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


def main() -> None:
    load_dotenv()
    admin_email = required("STK_BOOTSTRAP_ADMIN_EMAIL", 3).lower()
    admin_name = required("STK_BOOTSTRAP_ADMIN_NAME", 2)
    admin_password = required("STK_BOOTSTRAP_ADMIN_PASSWORD", 12)
    client_id = required("STK_BOOTSTRAP_SERVICE_CLIENT_ID", 3).lower()
    service_name = required("STK_BOOTSTRAP_SERVICE_NAME", 2)
    client_secret = required("STK_BOOTSTRAP_SERVICE_SECRET", 16)
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
        if admin_role is None or integration_role is None:
            raise SystemExit("Papéis fundacionais ausentes; execute o seed")

        user = session.scalar(select(User).where(User.email == admin_email))
        if user is None:
            admin_actor = Actor(
                organization_id=organization.id,
                kind="user",
                display_name=admin_name,
            )
            session.add(admin_actor)
            session.flush()
            user = User(
                actor_id=admin_actor.id,
                email=admin_email,
                password_hash=hash_secret(admin_password),
            )
            session.add(user)
        else:
            admin_actor = session.get(Actor, user.actor_id)
            if admin_actor is None:
                raise SystemExit("Usuário sem ator correspondente")
            admin_actor.display_name = admin_name
            user.password_hash = hash_secret(admin_password)
        attach_role(session, admin_actor, admin_role)

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
            service.secret_hash = hash_secret(client_secret)
        attach_role(session, service_actor, integration_role)
    print("Identidades locais configuradas sem exibir credenciais.")


if __name__ == "__main__":
    main()

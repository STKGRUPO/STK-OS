from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from stk_os.fiscal.certificate_vault import decrypt, encrypt
from stk_os.models import (
    BillingItem,
    BusinessUnit,
    Company,
    FiscalArchiveJob,
    FiscalDocument,
    FiscalIssuance,
    IntegrationConnection,
)

SCOPES = "openid profile offline_access Files.ReadWrite"
AUTHORITY = "https://login.microsoftonline.com/common/oauth2/v2.0"
GRAPH = "https://graph.microsoft.com/v1.0"
MONTHS = (
    "",
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
)
logger = logging.getLogger(__name__)


class OneDriveError(RuntimeError):
    pass


def microsoft_settings() -> tuple[str, str, str]:
    values = (
        os.environ.get("MICROSOFT_CLIENT_ID", ""),
        os.environ.get("MICROSOFT_CLIENT_SECRET", ""),
        os.environ.get("MICROSOFT_REDIRECT_URI", ""),
    )
    if not all(values):
        raise OneDriveError("Integração Microsoft não configurada")
    return values


def create_oauth_state(session: Session, organization_id: uuid.UUID, actor_id: uuid.UUID) -> str:
    from stk_os.models import IntegrationOAuthState

    state = secrets.token_urlsafe(32)
    session.add(
        IntegrationOAuthState(
            state_sha256=hashlib.sha256(state.encode()).hexdigest(),
            organization_id=organization_id,
            requested_by_actor_id=actor_id,
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
    )
    return state


def authorization_url(state: str) -> str:
    client_id, _secret, redirect_uri = microsoft_settings()
    query = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "response_mode": "query",
            "scope": SCOPES,
            "state": state,
        }
    )
    return f"{AUTHORITY}/authorize?{query}"


def _json_request(
    url: str,
    *,
    method: str = "GET",
    token: str | None = None,
    data: bytes | None = None,
    content_type: str = "application/json",
    accepted_errors: tuple[int, ...] = (),
) -> dict[str, Any]:
    if not url.startswith((AUTHORITY, GRAPH)):
        raise OneDriveError("Destino Microsoft inválido")
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        headers["Content-Type"] = content_type
    try:
        with urllib.request.urlopen(  # noqa: S310 - URLs are fixed Microsoft HTTPS endpoints.
            urllib.request.Request(  # noqa: S310 - validated Microsoft HTTPS URL.
                url, data=data, headers=headers, method=method
            ),
            timeout=30,
        ) as response:
            content = response.read()
            return json.loads(content) if content else {}
    except urllib.error.HTTPError as error:
        if error.code in accepted_errors:
            return {"http_status": error.code}
        raise OneDriveError("Microsoft Graph indisponível") from error
    except (urllib.error.URLError, ValueError) as error:
        raise OneDriveError("Microsoft Graph indisponível") from error


def exchange_code(code: str) -> dict[str, Any]:
    client_id, secret, redirect_uri = microsoft_settings()
    data = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "client_secret": secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "scope": SCOPES,
        }
    ).encode()
    return _json_request(
        f"{AUTHORITY}/token",
        method="POST",
        data=data,
        content_type="application/x-www-form-urlencoded",
    )


def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    client_id, secret, redirect_uri = microsoft_settings()
    data = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "client_secret": secret,
            "refresh_token": refresh_token,
            "redirect_uri": redirect_uri,
            "grant_type": "refresh_token",
            "scope": SCOPES,
        }
    ).encode()
    return _json_request(
        f"{AUTHORITY}/token",
        method="POST",
        data=data,
        content_type="application/x-www-form-urlencoded",
    )


def store_connection(
    session: Session, organization_id: uuid.UUID, tokens: dict[str, Any]
) -> IntegrationConnection:
    access = str(tokens.get("access_token") or "")
    refresh = str(tokens.get("refresh_token") or "")
    if not access or not refresh:
        raise OneDriveError("Microsoft não retornou credenciais renováveis")
    profile = _json_request(f"{GRAPH}/me", token=access)
    access_ciphertext, access_nonce = encrypt(access.encode())
    refresh_ciphertext, refresh_nonce = encrypt(refresh.encode())
    connection = session.scalar(
        select(IntegrationConnection).where(
            IntegrationConnection.organization_id == organization_id,
            IntegrationConnection.provider == "onedrive",
        )
    )
    if connection is None:
        connection = IntegrationConnection(
            organization_id=organization_id,
            provider="onedrive",
            access_token_ciphertext=access_ciphertext,
            access_token_nonce=access_nonce,
            refresh_token_ciphertext=refresh_ciphertext,
            refresh_token_nonce=refresh_nonce,
            token_expires_at=datetime.now(UTC),
            scopes=SCOPES,
        )
        session.add(connection)
    connection.account_id = str(profile.get("id") or "") or None
    connection.account_name = str(profile.get("displayName") or "") or None
    connection.access_token_ciphertext = access_ciphertext
    connection.access_token_nonce = access_nonce
    connection.refresh_token_ciphertext = refresh_ciphertext
    connection.refresh_token_nonce = refresh_nonce
    connection.token_expires_at = datetime.now(UTC) + timedelta(
        seconds=int(tokens.get("expires_in", 3600))
    )
    connection.scopes = str(tokens.get("scope") or SCOPES)
    connection.status = "active"
    return connection


def access_token(session: Session, connection: IntegrationConnection) -> str:
    if connection.token_expires_at > datetime.now(UTC) + timedelta(minutes=2):
        return decrypt(connection.access_token_ciphertext, connection.access_token_nonce).decode()
    refresh = decrypt(connection.refresh_token_ciphertext, connection.refresh_token_nonce).decode()
    tokens = refresh_access_token(refresh)
    refreshed = store_connection(session, connection.organization_id, tokens)
    return decrypt(refreshed.access_token_ciphertext, refreshed.access_token_nonce).decode()


def sanitize_component(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", value).strip().rstrip(".")
    return re.sub(r"\s+", " ", cleaned) or "SEM NOME"


def enqueue_archive(session: Session, issuance: FiscalIssuance) -> FiscalArchiveJob | None:
    if issuance.status != "completed" or not issuance.nfse_number:
        return None
    document_types = set(
        session.scalars(
            select(FiscalDocument.document_type).where(
                FiscalDocument.issuance_id == issuance.id,
                FiscalDocument.status == "available",
                FiscalDocument.content_bytes.is_not(None),
                FiscalDocument.document_type.in_(("nfse_xml", "danfse_pdf")),
            )
        )
    )
    if document_types != {"nfse_xml", "danfse_pdf"}:
        return None
    existing = session.scalar(
        select(FiscalArchiveJob).where(
            FiscalArchiveJob.issuance_id == issuance.id,
            FiscalArchiveJob.provider == "onedrive",
        )
    )
    if existing:
        return existing
    job = FiscalArchiveJob(
        organization_id=issuance.organization_id,
        issuance_id=issuance.id,
        provider="onedrive",
        status="pending",
    )
    session.add(job)
    session.flush()
    return job


def _put_file(token: str, path: str, content: bytes, content_type: str) -> None:
    encoded = urllib.parse.quote(path, safe="/")
    _json_request(
        f"{GRAPH}/me/drive/root:/{encoded}:/content",
        method="PUT",
        token=token,
        data=content,
        content_type=content_type,
    )


def _ensure_directory(token: str, directory: PurePosixPath) -> None:
    parent = PurePosixPath()
    for part in directory.parts:
        parent_address = (
            f"root:/{urllib.parse.quote(str(parent), safe='/')}:/children"
            if parent.parts
            else "root/children"
        )
        result = _json_request(
            f"{GRAPH}/me/drive/{parent_address}",
            method="POST",
            token=token,
            data=json.dumps(
                {
                    "name": part,
                    "folder": {},
                    "@microsoft.graph.conflictBehavior": "fail",
                }
            ).encode(),
            accepted_errors=(409,),
        )
        if result.get("http_status") not in (None, 409):
            raise OneDriveError("Não foi possível preparar a pasta no OneDrive")
        parent /= part


def archive_job(session: Session, job: FiscalArchiveJob) -> None:
    if job.status == "completed":
        return
    issuance = session.get(FiscalIssuance, job.issuance_id)
    item = session.get(BillingItem, issuance.billing_item_id) if issuance else None
    unit = session.get(BusinessUnit, item.business_unit_id) if item else None
    customer = session.get(Company, item.customer_company_id) if item else None
    connection = session.scalar(
        select(IntegrationConnection).where(
            IntegrationConnection.organization_id == job.organization_id,
            IntegrationConnection.provider == "onedrive",
            IntegrationConnection.status == "active",
        )
    )
    documents = list(
        session.scalars(select(FiscalDocument).where(FiscalDocument.issuance_id == job.issuance_id))
    )
    if not issuance or not item or not unit or not customer or not connection:
        raise OneDriveError("Dados ou conexão indisponíveis para arquivamento")
    by_type = {document.document_type: document for document in documents}
    required = ("nfse_xml", "danfse_pdf")
    if any(by_type.get(kind) is None or by_type[kind].content_bytes is None for kind in required):
        raise OneDriveError("Documentos fiscais persistidos estão incompletos")
    competence = item.competence_month
    directory = PurePosixPath(
        "STK GRUPO",
        "Financeiro",
        "NFS-e",
        sanitize_component(unit.name),
        str(competence.year),
        f"{competence.month:02d} - {MONTHS[competence.month]}",
    )
    client = sanitize_component(customer.trade_name or customer.legal_name).replace(" ", "_")
    token = access_token(session, connection)
    _ensure_directory(token, directory)
    for kind, extension, content_type in (
        ("danfse_pdf", "pdf", "application/pdf"),
        ("nfse_xml", "xml", "application/xml"),
    ):
        document = by_type[kind]
        filename = f"NFSE_{issuance.nfse_number}_{client}.{extension}"
        _put_file(token, str(directory / filename), document.content_bytes, content_type)
    job.status = "completed"
    job.last_error = None
    job.remote_path = str(directory)
    job.archived_at = datetime.now(UTC)


def process_pending(session: Session, organization_id: uuid.UUID) -> tuple[int, int]:
    connection = session.scalar(
        select(IntegrationConnection).where(
            IntegrationConnection.organization_id == organization_id,
            IntegrationConnection.provider == "onedrive",
            IntegrationConnection.status == "active",
        )
    )
    if connection is None:
        return 0, 0
    candidates = list(
        session.scalars(
            select(FiscalIssuance).where(
                FiscalIssuance.organization_id == organization_id,
                FiscalIssuance.status == "completed",
                FiscalIssuance.nfse_number.is_not(None),
            )
        )
    )
    for issuance in candidates:
        enqueue_archive(session, issuance)
    session.flush()
    jobs = list(
        session.scalars(
            select(FiscalArchiveJob).where(
                FiscalArchiveJob.organization_id == organization_id,
                FiscalArchiveJob.provider == "onedrive",
                FiscalArchiveJob.status.in_(("pending", "failed")),
            )
        )
    )
    completed = 0
    for job in jobs:
        job.attempts += 1
        try:
            archive_job(session, job)
            completed += 1
        except Exception as error:
            job.status = "failed"
            job.last_error = str(error)[:500]
    return completed, len(jobs) - completed


def process_pending_in_background(organization_id: uuid.UUID) -> None:
    from sqlalchemy.orm import sessionmaker

    from stk_os.database import get_engine

    try:
        with sessionmaker(bind=get_engine(), expire_on_commit=False)() as session:
            process_pending(session, organization_id)
            session.commit()
    except Exception:
        logger.exception(
            "onedrive_background_archive_failed",
            extra={"organization_id": str(organization_id)},
        )

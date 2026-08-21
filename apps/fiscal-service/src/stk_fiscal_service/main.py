from __future__ import annotations

import base64
import hashlib
import secrets
import ssl
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from stk_os.fiscal.provider import ProviderResult, SefinGateway
from stk_os.fiscal.signing import (
    CertificateConfigurationError,
    MountedSecretResolver,
    XmlSigner,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STK_FISCAL_SERVICE_", extra="ignore")

    token_file: Path = Path("/run/secrets/stk-fiscal-service/token")
    secret_mount_root: Path = Path("/run/secrets/stk-fiscal")
    allowed_hosts: str = "sefin.nfse.gov.br,sefin.producaorestrita.nfse.gov.br"
    timeout_seconds: int = Field(default=60, ge=5, le=120)


@lru_cache
def settings() -> Settings:
    return Settings()


class IssueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoint: str
    dps_id: str = Field(min_length=20, max_length=100)
    certificate_key_id: str = Field(min_length=1, max_length=255)
    unsigned_xml_b64: str = Field(min_length=20, max_length=3_000_000)


class ReconcileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_base_url: str
    dps_id: str = Field(min_length=20, max_length=100)
    certificate_key_id: str = Field(min_length=1, max_length=255)


class DocumentResponse(BaseModel):
    document_type: str
    content_type: str
    content_b64: str


class ResultResponse(BaseModel):
    status: str
    http_status: int | None = None
    nfse_number: str | None = None
    access_key: str | None = None
    provider_reference: str | None = None
    error_code: str | None = None
    detail: str | None = None
    signed_dps_sha256: str | None = None
    documents: list[DocumentResponse] = []


bearer = HTTPBearer(auto_error=False)


def authorize(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    try:
        expected = settings().token_file.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise HTTPException(
            status_code=503, detail="Identidade M2M não provisionada"
        ) from error
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not secrets.compare_digest(credentials.credentials, expected)
    ):
        raise HTTPException(status_code=401, detail="Credencial M2M inválida")


def gateway(certificate_key_id: str) -> tuple[SefinGateway, object]:
    config = settings()
    resolver = MountedSecretResolver(config.secret_mount_root)
    material = resolver.resolve(certificate_key_id)
    directory = (
        config.secret_mount_root / certificate_key_id.replace("-", "_")
    ).resolve()
    context = ssl.create_default_context()
    password = (
        material.private_key_password.decode()
        if material.private_key_password
        else None
    )
    context.load_cert_chain(
        directory / "certificate.pem", directory / "private-key.pem", password=password
    )
    client = SefinGateway(
        context,
        allowed_hosts=frozenset(
            host.strip() for host in config.allowed_hosts.split(",") if host.strip()
        ),
        timeout=config.timeout_seconds,
    )
    return client, material


def response(
    result: ProviderResult, *, signed_hash: str | None = None
) -> ResultResponse:
    return ResultResponse(
        status=result.status,
        http_status=result.http_status,
        nfse_number=result.nfse_number,
        access_key=result.access_key,
        provider_reference=result.provider_reference,
        error_code=result.error_code,
        detail=result.detail,
        signed_dps_sha256=signed_hash,
        documents=[
            DocumentResponse(
                document_type=item.document_type,
                content_type=item.content_type,
                content_b64=base64.b64encode(item.content).decode(),
            )
            for item in result.documents
        ],
    )


app = FastAPI(
    title="STK Fiscal Service",
    version="0.1.0",
    description="Serviço privado de assinatura, emissão e reconciliação NFS-e.",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/internal/v1/issue",
    response_model=ResultResponse,
    dependencies=[Depends(authorize)],
)
def issue(command: IssueRequest) -> ResultResponse:
    try:
        unsigned = base64.b64decode(command.unsigned_xml_b64, validate=True)
        client, material = gateway(command.certificate_key_id)
        signed = XmlSigner().sign(unsigned, material)  # type: ignore[arg-type]
    except (ValueError, CertificateConfigurationError) as error:
        return ResultResponse(
            status="external_unavailable",
            error_code="CERTIFICATE_INVALID",
            detail=str(error),
        )
    result = client.issue(
        endpoint=command.endpoint, dps_id=command.dps_id, signed_xml=signed
    )
    return response(result, signed_hash=hashlib.sha256(signed).hexdigest())


@app.post(
    "/internal/v1/reconcile",
    response_model=ResultResponse,
    dependencies=[Depends(authorize)],
)
def reconcile(command: ReconcileRequest) -> ResultResponse:
    try:
        client, _material = gateway(command.certificate_key_id)
    except CertificateConfigurationError as error:
        return ResultResponse(
            status="external_unavailable",
            error_code="CERTIFICATE_INVALID",
            detail=str(error),
        )
    return response(
        client.reconcile(query_base_url=command.query_base_url, dps_id=command.dps_id)
    )

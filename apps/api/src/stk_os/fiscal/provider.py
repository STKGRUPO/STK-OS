from __future__ import annotations

import base64
import gzip
import json
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Literal, Protocol
from urllib.parse import quote, urlparse

ProviderStatus = Literal["completed", "rejected", "not_found", "uncertain", "external_unavailable"]


@dataclass(frozen=True)
class ProviderDocument:
    document_type: str
    content_type: str
    content: bytes


@dataclass(frozen=True)
class ProviderResult:
    status: ProviderStatus
    http_status: int | None = None
    nfse_number: str | None = None
    access_key: str | None = None
    provider_reference: str | None = None
    error_code: str | None = None
    detail: str | None = None
    signed_dps_sha256: str | None = None
    documents: tuple[ProviderDocument, ...] = field(default_factory=tuple)


class FiscalGateway(Protocol):
    def issue(self, *, endpoint: str, dps_id: str, signed_xml: bytes) -> ProviderResult: ...

    def reconcile(self, *, query_base_url: str, dps_id: str) -> ProviderResult: ...


def _safe_detail(data: object) -> str:
    if isinstance(data, dict):
        errors = data.get("erros") or data.get("mensagem") or data.get("message")
        return json.dumps(errors, ensure_ascii=False)[:1000]
    return "Resposta externa não reconhecida"


class SefinGateway:
    """Cliente SEFIN sem retry de emissão e com mTLS carregado de volume de secrets."""

    def __init__(
        self, ssl_context: ssl.SSLContext, *, allowed_hosts: frozenset[str], timeout: int = 60
    ):
        self.ssl_context = ssl_context
        self.allowed_hosts = allowed_hosts
        self.timeout = timeout

    def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.hostname not in self.allowed_hosts
        ):
            raise ValueError("Endpoint fiscal fora da allowlist")

    def _request(self, request: urllib.request.Request) -> tuple[int, dict[str, object]]:
        self._validate_url(request.full_url)
        try:
            with urllib.request.urlopen(  # noqa: S310 - URL validada por allowlist estrita
                request, context=self.ssl_context, timeout=self.timeout
            ) as response:
                raw = response.read(2_000_000)
                return response.status, json.loads(raw)
        except urllib.error.HTTPError as error:
            raw = error.read(256_000)
            try:
                return error.code, json.loads(raw)
            except json.JSONDecodeError:
                return error.code, {}

    def issue(self, *, endpoint: str, dps_id: str, signed_xml: bytes) -> ProviderResult:
        payload = json.dumps(
            {"dpsXmlGZipB64": base64.b64encode(gzip.compress(signed_xml)).decode("ascii")}
        ).encode()
        request = urllib.request.Request(  # noqa: S310 - HTTPS validado antes do envio
            endpoint,
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            status, data = self._request(request)
        except (TimeoutError, urllib.error.URLError):
            return ProviderResult(status="uncertain", error_code="TRANSMISSION_UNCERTAIN")
        if status == 201:
            compressed = data.get("nfseXmlGZipB64")
            try:
                xml = gzip.decompress(base64.b64decode(str(compressed)))
            except Exception:
                return ProviderResult(
                    status="uncertain", http_status=status, error_code="AUTHORIZED_RESPONSE_INVALID"
                )
            return ProviderResult(
                status="completed",
                http_status=status,
                nfse_number=str(data.get("numero") or data.get("nNFSe") or "SEM_NUMERO"),
                access_key=str(data.get("chaveAcesso") or ""),
                provider_reference=dps_id,
                documents=(ProviderDocument("nfse_xml", "application/xml", xml),),
            )
        if status in (400, 409, 422):
            return ProviderResult(
                status="rejected",
                http_status=status,
                error_code="FISCAL_REJECTION",
                detail=_safe_detail(data),
            )
        if status == 429 or status >= 500:
            return ProviderResult(
                status="external_unavailable", http_status=status, error_code="SEFIN_UNAVAILABLE"
            )
        return ProviderResult(
            status="uncertain", http_status=status, error_code="AMBIGUOUS_RESPONSE"
        )

    def reconcile(self, *, query_base_url: str, dps_id: str) -> ProviderResult:
        url = f"{query_base_url.rstrip('/')}/dps/{quote(dps_id, safe='')}"
        try:
            status, data = self._request(
                urllib.request.Request(  # noqa: S310 - HTTPS validado antes do envio
                    url, method="GET", headers={"Accept": "application/json"}
                )
            )
        except (TimeoutError, urllib.error.URLError):
            return ProviderResult(status="uncertain", error_code="RECONCILIATION_UNAVAILABLE")
        if status == 404:
            return ProviderResult(status="not_found", http_status=status)
        access_key = str(data.get("chaveAcesso") or "")
        if status == 200 and access_key:
            return ProviderResult(
                status="completed",
                http_status=status,
                nfse_number=str(data.get("numero") or data.get("nNFSe") or "SEM_NUMERO"),
                access_key=access_key,
                provider_reference=dps_id,
            )
        return ProviderResult(
            status="uncertain", http_status=status, error_code="RECONCILIATION_AMBIGUOUS"
        )


class RemoteFiscalServiceGateway:
    """Cliente do serviço fiscal privado; o backend nunca recebe o A1."""

    def __init__(
        self,
        service_url: str,
        token: str,
        certificate_key_id: str,
        *,
        timeout: int = 60,
    ):
        parsed = urlparse(service_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("STK_FISCAL_SERVICE_URL deve usar HTTPS")
        self.service_url = service_url.rstrip("/")
        self.token = token
        self.certificate_key_id = certificate_key_id
        self.timeout = timeout

    def _call(self, path: str, payload: dict[str, object]) -> ProviderResult:
        request = urllib.request.Request(  # noqa: S310 - URL HTTPS validada no construtor
            f"{self.service_url}{path}",
            data=json.dumps(payload).encode(),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                data = json.loads(response.read(4_000_000))
        except (TimeoutError, urllib.error.URLError):
            return ProviderResult(status="uncertain", error_code="FISCAL_SERVICE_UNAVAILABLE")
        documents = tuple(
            ProviderDocument(
                document_type=str(item["document_type"]),
                content_type=str(item["content_type"]),
                content=base64.b64decode(str(item["content_b64"])),
            )
            for item in data.get("documents", [])
        )
        return ProviderResult(
            status=data["status"],
            http_status=data.get("http_status"),
            nfse_number=data.get("nfse_number"),
            access_key=data.get("access_key"),
            provider_reference=data.get("provider_reference"),
            error_code=data.get("error_code"),
            detail=data.get("detail"),
            signed_dps_sha256=data.get("signed_dps_sha256"),
            documents=documents,
        )

    def issue(self, *, endpoint: str, dps_id: str, signed_xml: bytes) -> ProviderResult:
        return self._call(
            "/internal/v1/issue",
            {
                "endpoint": endpoint,
                "dps_id": dps_id,
                "certificate_key_id": self.certificate_key_id,
                "unsigned_xml_b64": base64.b64encode(signed_xml).decode(),
            },
        )

    def reconcile(self, *, query_base_url: str, dps_id: str) -> ProviderResult:
        return self._call(
            "/internal/v1/reconcile",
            {
                "query_base_url": query_base_url,
                "dps_id": dps_id,
                "certificate_key_id": self.certificate_key_id,
            },
        )

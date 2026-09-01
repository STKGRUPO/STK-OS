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

from stk_os.fiscal.documents import AuthorizedNfseError, extract_authorized_nfse_metadata

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

    def fetch_authorized_nfse(
        self, *, query_base_url: str, access_key: str, dps_id: str
    ) -> ProviderResult: ...


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

    @staticmethod
    def _authorized_result(
        data: dict[str, object], *, http_status: int, dps_id: str
    ) -> ProviderResult:
        compressed = data.get("nfseXmlGZipB64")
        try:
            xml = gzip.decompress(base64.b64decode(str(compressed)))
            metadata = extract_authorized_nfse_metadata(xml)
        except (AuthorizedNfseError, OSError, ValueError):
            return ProviderResult(
                status="uncertain",
                http_status=http_status,
                error_code="AUTHORIZED_RESPONSE_INVALID",
            )
        return ProviderResult(
            status="completed",
            http_status=http_status,
            nfse_number=metadata.nfse_number,
            access_key=metadata.access_key,
            provider_reference=dps_id,
            documents=(ProviderDocument("nfse_xml", "application/xml", xml),),
        )

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
            return self._authorized_result(data, http_status=status, dps_id=dps_id)
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
            nfse_url = f"{query_base_url.rstrip('/')}/nfse/{quote(access_key, safe='')}"
            try:
                nfse_status, nfse_data = self._request(
                    urllib.request.Request(  # noqa: S310 - HTTPS validado por allowlist
                        nfse_url, method="GET", headers={"Accept": "application/json"}
                    )
                )
            except (TimeoutError, urllib.error.URLError):
                return ProviderResult(
                    status="uncertain", error_code="AUTHORIZED_DOCUMENT_UNAVAILABLE"
                )
            if nfse_status == 200:
                return self._authorized_result(nfse_data, http_status=nfse_status, dps_id=dps_id)
            return ProviderResult(
                status="uncertain",
                http_status=nfse_status,
                error_code="AUTHORIZED_DOCUMENT_UNAVAILABLE",
            )
        return ProviderResult(
            status="uncertain", http_status=status, error_code="RECONCILIATION_AMBIGUOUS"
        )

    def fetch_authorized_nfse(
        self, *, query_base_url: str, access_key: str, dps_id: str
    ) -> ProviderResult:
        url = f"{query_base_url.rstrip('/')}/nfse/{quote(access_key, safe='')}"
        try:
            status, data = self._request(
                urllib.request.Request(  # noqa: S310 - HTTPS validado por allowlist
                    url, method="GET", headers={"Accept": "application/json"}
                )
            )
        except (TimeoutError, urllib.error.URLError):
            return ProviderResult(
                status="external_unavailable",
                error_code="AUTHORIZED_DOCUMENT_UNAVAILABLE",
            )
        if status == 200:
            return self._authorized_result(data, http_status=status, dps_id=dps_id)
        if status == 404:
            return ProviderResult(
                status="not_found",
                http_status=status,
                error_code="AUTHORIZED_DOCUMENT_NOT_FOUND",
            )
        if status == 429 or status >= 500:
            return ProviderResult(
                status="external_unavailable",
                http_status=status,
                error_code="AUTHORIZED_DOCUMENT_UNAVAILABLE",
            )
        return ProviderResult(
            status="uncertain",
            http_status=status,
            error_code="AUTHORIZED_DOCUMENT_RESPONSE_INVALID",
        )


class LocalSigningGateway:
    """Assina o DPS na própria API e transmite direto ao SEFIN via mTLS."""

    def __init__(self, transport: SefinGateway, signer, material):
        self.transport = transport
        self.signer = signer
        self.material = material

    def issue(self, *, endpoint: str, dps_id: str, signed_xml: bytes) -> ProviderResult:
        signed = self.signer.sign(signed_xml, self.material)
        head = signed[:400].decode("utf-8", "ignore")
        if 'xmlns="http://www.sped.fazenda.gov.br/nfse"' not in head or "<ns" in head:
            raise RuntimeError(f"DPS com namespace invalido (E1228). Inicio do XML: {head}")
        result = self.transport.issue(endpoint=endpoint, dps_id=dps_id, signed_xml=signed)
        import hashlib

        return ProviderResult(
            status=result.status,
            http_status=result.http_status,
            nfse_number=result.nfse_number,
            access_key=result.access_key,
            provider_reference=result.provider_reference,
            error_code=result.error_code,
            detail=result.detail,
            signed_dps_sha256=hashlib.sha256(signed).hexdigest(),
            documents=result.documents,
        )

    def reconcile(self, *, query_base_url: str, dps_id: str) -> ProviderResult:
        return self.transport.reconcile(query_base_url=query_base_url, dps_id=dps_id)

    def fetch_authorized_nfse(
        self, *, query_base_url: str, access_key: str, dps_id: str
    ) -> ProviderResult:
        return self.transport.fetch_authorized_nfse(
            query_base_url=query_base_url,
            access_key=access_key,
            dps_id=dps_id,
        )

from __future__ import annotations

from dataclasses import dataclass

from stk_os.config import get_settings
from stk_os.fiscal.provider import FiscalGateway, RemoteFiscalServiceGateway
from stk_os.fiscal.storage import PrivateFilesystemDocumentStore
from stk_os.models import FiscalEstablishmentConfig


@dataclass
class FiscalRuntime:
    document_store: PrivateFilesystemDocumentStore

    def gateway_for(self, config: FiscalEstablishmentConfig) -> FiscalGateway:
        settings = get_settings()
        try:
            token = settings.fiscal_service_token_file.read_text(encoding="utf-8").strip()
        except OSError as error:
            raise RuntimeError("Token do serviço fiscal privado não provisionado") from error
        return RemoteFiscalServiceGateway(
            settings.fiscal_service_url,
            token,
            config.certificate_key_id,
            timeout=settings.fiscal_timeout_seconds,
        )


def get_fiscal_runtime() -> FiscalRuntime:
    settings = get_settings()
    return FiscalRuntime(
        document_store=PrivateFilesystemDocumentStore(settings.fiscal_document_root),
    )

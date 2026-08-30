from __future__ import annotations

from dataclasses import dataclass

from stk_os.config import get_settings
from stk_os.fiscal import certificate_vault
from stk_os.fiscal.provider import FiscalGateway, LocalSigningGateway, SefinGateway
from stk_os.fiscal.signing import XmlSigner
from stk_os.fiscal.storage import PrivateFilesystemDocumentStore
from stk_os.models import FiscalEstablishmentConfig

SEFIN_HOSTS = frozenset(
    {
        "sefin.nfse.gov.br",
        "sefin.producaorestrita.nfse.gov.br",
        "adn.nfse.gov.br",
        "adn.producaorestrita.nfse.gov.br",
    }
)


@dataclass
class FiscalRuntime:
    document_store: PrivateFilesystemDocumentStore

    def gateway_for(self, session, config: FiscalEstablishmentConfig) -> FiscalGateway:
        settings = get_settings()
        material = certificate_vault.material_for(session, config)
        ssl_context = certificate_vault.ssl_context_for(session, config)
        transport = SefinGateway(
            ssl_context,
            allowed_hosts=SEFIN_HOSTS,
            timeout=settings.fiscal_timeout_seconds,
        )
        return LocalSigningGateway(transport, XmlSigner(), material)


def get_fiscal_runtime() -> FiscalRuntime:
    settings = get_settings()
    return FiscalRuntime(PrivateFilesystemDocumentStore(settings.fiscal_document_root))

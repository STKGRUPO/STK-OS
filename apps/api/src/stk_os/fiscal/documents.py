from __future__ import annotations

import re
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from stk_os.fiscal.danfse import generate_danfse

NFSE_NAMESPACE = "http://www.sped.fazenda.gov.br/nfse"
NS = {"n": NFSE_NAMESPACE}
WINDOWS_RESERVED_NAMES = {
    "AUX",
    "CON",
    "NUL",
    "PRN",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


class AuthorizedNfseError(ValueError):
    """O XML retornado não representa uma NFS-e autorizada utilizável."""


@dataclass(frozen=True)
class AuthorizedNfseMetadata:
    nfse_number: str
    access_key: str
    dps_number: str


def parse_authorized_nfse(xml: bytes) -> tuple[etree._Element, AuthorizedNfseMetadata]:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
    try:
        root = etree.fromstring(xml, parser=parser)
    except etree.XMLSyntaxError as error:
        raise AuthorizedNfseError("XML autorizado inválido") from error
    if root.tag != f"{{{NFSE_NAMESPACE}}}NFSe":
        raise AuthorizedNfseError("Documento retornado não é uma NFS-e nacional")
    inf = root.find("n:infNFSe", namespaces=NS)
    if inf is None:
        raise AuthorizedNfseError("XML autorizado sem infNFSe")
    nfse_number = (inf.findtext("n:nNFSe", namespaces=NS) or "").strip()
    identifier = (inf.get("Id") or "").strip()
    access_key = identifier[3:] if identifier.startswith("NFS") else identifier
    dps_number = (inf.findtext(".//n:infDPS/n:nDPS", namespaces=NS) or "").strip()
    if not nfse_number:
        raise AuthorizedNfseError("XML autorizado sem nNFSe")
    if len(access_key) != 50 or not access_key.isdigit():
        raise AuthorizedNfseError("XML autorizado sem chave de acesso válida")
    if not dps_number:
        raise AuthorizedNfseError("XML autorizado sem número da DPS")
    return root, AuthorizedNfseMetadata(nfse_number, access_key, dps_number)


def extract_authorized_nfse_metadata(xml: bytes) -> AuthorizedNfseMetadata:
    return parse_authorized_nfse(xml)[1]


def filename_token(value: str, *, fallback: str = "CLIENTE", max_length: int = 80) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", normalized).strip("_.").upper()
    normalized = re.sub(r"_+", "_", normalized)[:max_length].rstrip("_.")
    if not normalized:
        normalized = fallback
    if normalized in WINDOWS_RESERVED_NAMES:
        normalized = f"{fallback}_{normalized}"
    return normalized


def friendly_nfse_filename(
    *,
    document_type: str,
    nfse_number: str,
    trade_name: str | None,
    legal_name: str,
) -> str:
    extension = {"nfse_xml": "xml", "danfse_pdf": "pdf"}.get(document_type)
    if extension is None:
        raise ValueError("Tipo de documento sem filename amigável")
    number = filename_token(nfse_number, fallback="SEM_NUMERO", max_length=30)
    customer = filename_token((trade_name or "").strip() or legal_name)
    return f"NFSE_{number}_{customer}.{extension}"


def render_danfse_from_authorized_xml(xml: bytes) -> bytes:
    # Valida antes de entregar os bytes ao gerador legado. O PDF não recebe
    # snapshot, dados do frontend ou qualquer outra fonte paralela.
    parse_authorized_nfse(xml)
    with tempfile.TemporaryDirectory(prefix="stk-danfse-") as temporary:
        directory = Path(temporary)
        xml_path = directory / "authorized-nfse.xml"
        pdf_path = directory / "danfse.pdf"
        xml_path.write_bytes(xml)
        generate_danfse(xml_path, pdf_path)
        return pdf_path.read_bytes()

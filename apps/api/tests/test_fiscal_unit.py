from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
from lxml import etree

from stk_os.fiscal.dps import build_dps
from stk_os.fiscal.engine import PROFILE_PROFESSIONAL, calculate
from stk_os.fiscal.signing import CertificateMaterial, XmlSigner
from stk_os.fiscal.storage import PrivateFilesystemDocumentStore

DS = "http://www.w3.org/2000/09/xmldsig#"
NFSE = "http://www.sped.fazenda.gov.br/nfse"


def snapshot(*, tax_regime: str = "lucro_presumido") -> dict[str, object]:
    return {
        "environment": "homologation",
        "competence_date": "2026-08-01",
        "gross_amount": "1000.00",
        "issuer": {
            "tax_id": "12345678000190",
            "municipality_code": "3550308",
        },
        "customer": {
            "tax_id": "19000000000001",
            "legal_name": "Cliente Sintético Ltda.",
            "municipality_code": "3550308",
            "postal_code": "01001000",
            "address_line": "Rua Sintética, 100",
        },
        "service_code": "010101",
        "service_description": "Consultoria sintética",
        "nbs_code": "101010100",
        "fiscal_rules": {
            "tax_regime": tax_regime,
            "service_profile": "servicos_profissionais",
            "iss_percent": "2.00",
            "pis_percent": "0.65",
            "cofins_percent": "3.00",
            "csll_percent": "1.00",
            "irrf_percent": "1.50",
        },
    }


def certificate_material() -> tuple[CertificateMaterial, rsa.RSAPrivateKey]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "STK Test A1")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .sign(key, hashes.SHA256())
    )
    return (
        CertificateMaterial(
            certificate.public_bytes(serialization.Encoding.PEM),
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ),
        ),
        key,
    )


def test_extracted_engine_preserves_threshold_and_simples_behavior() -> None:
    regular = calculate(
        {
            "tax_regime": "lucro_presumido",
            "fiscal": {"social_retention_min": "10.00", "irrf_retention_min": "10.00"},
        },
        PROFILE_PROFESSIONAL,
        Decimal("1000.00"),
    )
    simple = calculate(
        {"tax_regime": "simples_nacional", "fiscal": {}},
        PROFILE_PROFESSIONAL,
        Decimal("1000.00"),
    )
    assert regular.social_retido == Decimal("46.50")
    assert regular.irrf_retido == Decimal("15.00")
    assert regular.liquido == Decimal("938.50")
    assert simple.federal_fields_mode == "omit"
    assert simple.total_retido == Decimal("0.00")


def test_dps_is_signed_in_memory_with_legacy_xmldsig_profile() -> None:
    unsigned, dps_identifier, _decision = build_dps(
        snapshot(), series=1, number=7, issued_at=datetime(2026, 8, 20, 12, tzinfo=UTC)
    )
    material, key = certificate_material()
    signed = XmlSigner().sign(unsigned, material)
    root = etree.fromstring(signed)
    signature = root.find(f"{{{DS}}}Signature")
    assert signature is not None
    signed_info = signature.find(f"{{{DS}}}SignedInfo")
    signature_value = signature.findtext(f"{{{DS}}}SignatureValue")
    assert signed_info is not None and signature_value
    key.public_key().verify(
        base64.b64decode(signature_value),
        etree.tostring(signed_info, method="c14n"),
        padding.PKCS1v15(),
        hashes.SHA1(),  # noqa: S303 - perfil homologado do legado
    )
    inf = root.find(f"{{{NFSE}}}infDPS")
    assert inf is not None and inf.get("Id") == dps_identifier
    expected_digest = base64.b64encode(
        hashlib.sha1(etree.tostring(inf, method="c14n"), usedforsecurity=False).digest()
    ).decode()
    assert signature.findtext(f".//{{{DS}}}DigestValue") == expected_digest


def test_private_document_store_rejects_path_escape(tmp_path) -> None:
    store = PrivateFilesystemDocumentStore(tmp_path / "private")
    with pytest.raises(ValueError, match="inválida"):
        store.path_for("../outside.xml")

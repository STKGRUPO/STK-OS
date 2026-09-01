from __future__ import annotations

import base64
import gzip
import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
from lxml import etree

from stk_os.fiscal import certificate_vault
from stk_os.fiscal.configuration import FiscalConfigurationError
from stk_os.fiscal.documents import (
    extract_authorized_nfse_metadata,
    friendly_nfse_filename,
    render_danfse_from_authorized_xml,
)
from stk_os.fiscal.dps import build_dps
from stk_os.fiscal.engine import PROFILE_PROFESSIONAL, calculate
from stk_os.fiscal.provider import SefinGateway
from stk_os.fiscal.signing import CertificateMaterial, XmlSigner, c14n
from stk_os.fiscal.storage import PrivateFilesystemDocumentStore

DS = "http://www.w3.org/2000/09/xmldsig#"
NFSE = "http://www.sped.fazenda.gov.br/nfse"
AUTHORIZED_NFSE_XML = (
    Path(__file__).parent / "fixtures" / "nfse_13_authorized_without_signatures.xml"
).read_bytes()


def mr_rules() -> dict[str, object]:
    return {
        "tax_regime": "lucro_presumido",
        "op_simp_nac": "1",
        "reg_esp_trib": "0",
        "service_profile": "servicos_profissionais",
        "trib_issqn": "1",
        "iss_percent": "2.00",
        "iss_retained_by_taker": False,
        "pis_cofins_cst": "01",
        "pis_cofins_retention_type": "automatic",
        "pis_percent": "0.65",
        "cofins_percent": "3.00",
        "csll_percent": "1.00",
        "irrf_percent": "1.50",
        "social_retention_applicable": True,
        "irrf_retention_applicable": True,
        "social_retention_min": "10.00",
        "irrf_retention_min": "10.00",
        "tot_trib_strategy": "percentual",
        "aprox_tributos_federal": "13.45",
        "aprox_tributos_estadual": "0.00",
        "aprox_tributos_municipal": "3.83",
    }


def st_rules() -> dict[str, object]:
    return {
        "tax_regime": "simples_nacional",
        "op_simp_nac": "3",
        "reg_ap_trib_sn": "1",
        "reg_esp_trib": "0",
        "service_profile": "perfil_empresa",
        "trib_issqn": "1",
        "iss_percent": "0.00",
        "iss_retained_by_taker": False,
        "pis_cofins_cst": "00",
        "pis_cofins_retention_type": "0",
        "tot_trib_strategy": "percentual",
        "aprox_tributos_federal": "13.45",
        "aprox_tributos_estadual": "0.00",
        "aprox_tributos_municipal": "3.83",
    }


def snapshot(*, issuer: str = "mr", complete_address: bool = True) -> dict[str, object]:
    is_st = issuer == "st"
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
            "address_number": "100" if complete_address else None,
            "address_complement": "Sala 1",
            "district": "Centro" if complete_address else None,
        },
        "service_code": "020101" if is_st else "010101",
        "service_description": "Consultoria sintética",
        "nbs_code": "114031000" if is_st else "101010100",
        "fiscal_rules": st_rules() if is_st else mr_rules(),
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
        {"tax_regime": "lucro_presumido", "fiscal": mr_rules()},
        PROFILE_PROFESSIONAL,
        Decimal("1000.00"),
    )
    simple = calculate(
        {"tax_regime": "simples_nacional", "fiscal": st_rules()},
        PROFILE_PROFESSIONAL,
        Decimal("1000.00"),
    )
    assert regular.social_retido == Decimal("46.50")
    assert regular.irrf_retido == Decimal("15.00")
    assert regular.liquido == Decimal("938.50")
    assert simple.federal_fields_mode == "omit"
    assert simple.total_retido == Decimal("0.00")


def fiscal_semantics(xml: bytes) -> dict[str, str | None]:
    root = etree.fromstring(xml)
    ns = {"n": NFSE}
    names = (
        "opSimpNac", "regApTribSN", "regEspTrib", "cTribNac", "cNBS",
        "tribISSQN", "tpRetISSQN", "CST", "tpRetPisCofins",
        "pTotTribFed", "pTotTribEst", "pTotTribMun", "indTotTrib",
    )
    return {name: root.findtext(f".//n:{name}", namespaces=ns) for name in names}


@pytest.mark.parametrize(
    ("gross_amount", "expected"),
    (
        (
            "120.00",
            {
                "vPis": "0.78",
                "vCofins": "3.60",
                "tpRetPisCofins": "0",
                "vRetIRRF": None,
                "vRetCSLL": None,
                "csll": Decimal("1.20"),
                "social_retido": Decimal("0.00"),
                "irrf_retido": Decimal("0.00"),
                "reter_social": False,
                "reter_irrf": False,
                "liquido": Decimal("120.00"),
            },
        ),
        (
            "450.00",
            {
                "vPis": "2.93",
                "vCofins": "13.50",
                "tpRetPisCofins": "3",
                "vRetIRRF": None,
                "vRetCSLL": "20.93",
                "csll": Decimal("4.50"),
                "social_retido": Decimal("20.93"),
                "irrf_retido": Decimal("0.00"),
                "reter_social": True,
                "reter_irrf": False,
                "liquido": Decimal("429.07"),
            },
        ),
        (
            "800.00",
            {
                "vPis": "5.20",
                "vCofins": "24.00",
                "tpRetPisCofins": "3",
                "vRetIRRF": "12.00",
                "vRetCSLL": "37.20",
                "csll": Decimal("8.00"),
                "social_retido": Decimal("37.20"),
                "irrf_retido": Decimal("12.00"),
                "reter_social": True,
                "reter_irrf": True,
                "liquido": Decimal("750.80"),
            },
        ),
        (
            "2750.00",
            {
                "vPis": "17.88",
                "vCofins": "82.50",
                "tpRetPisCofins": "3",
                "vRetIRRF": "41.25",
                "vRetCSLL": "127.88",
                "csll": Decimal("27.50"),
                "social_retido": Decimal("127.88"),
                "irrf_retido": Decimal("41.25"),
                "reter_social": True,
                "reter_irrf": True,
                "liquido": Decimal("2580.87"),
            },
        ),
    ),
)
def test_mr_build_dps_matches_four_authorized_golden_samples(
    gross_amount: str,
    expected: dict[str, str | Decimal | bool | None],
) -> None:
    current = snapshot(issuer="mr")
    current["gross_amount"] = gross_amount
    xml, _, decision = build_dps(
        current,
        series=1,
        number=1,
        issued_at=datetime(2026, 8, 20, 12, tzinfo=UTC),
    )
    root = etree.fromstring(xml)
    ns = {"n": NFSE}

    assert {
        name: root.findtext(f".//n:{name}", namespaces=ns)
        for name in (
            "opSimpNac",
            "regEspTrib",
            "tribISSQN",
            "tpRetISSQN",
            "CST",
            "pTotTribFed",
            "pTotTribEst",
            "pTotTribMun",
            "pTotTribSN",
            "indTotTrib",
        )
    } == {
        "opSimpNac": "1",
        "regEspTrib": "0",
        "tribISSQN": "1",
        "tpRetISSQN": "1",
        "CST": "01",
        "pTotTribFed": "13.45",
        "pTotTribEst": "0.00",
        "pTotTribMun": "3.83",
        "pTotTribSN": None,
        "indTotTrib": None,
    }
    for name in ("vPis", "vCofins", "tpRetPisCofins", "vRetIRRF", "vRetCSLL"):
        assert root.findtext(f".//n:{name}", namespaces=ns) == expected[name]
    assert decision.csll == expected["csll"]
    assert decision.social_retido == expected["social_retido"]
    assert decision.irrf_retido == expected["irrf_retido"]
    assert decision.reter_social is expected["reter_social"]
    assert decision.reter_irrf is expected["reter_irrf"]
    assert decision.liquido == expected["liquido"]


def test_multiissuer_rules_are_isolated_and_st_matches_authorized_semantics() -> None:
    mr_first, _, _ = build_dps(
        snapshot(issuer="mr"), series=1, number=1, issued_at=datetime.now(UTC)
    )
    st, _, _ = build_dps(
        snapshot(issuer="st"), series=1, number=2, issued_at=datetime.now(UTC)
    )
    mr_second, _, _ = build_dps(
        snapshot(issuer="mr"), series=1, number=3, issued_at=datetime.now(UTC)
    )
    assert fiscal_semantics(mr_first) == fiscal_semantics(mr_second)
    assert fiscal_semantics(st) == {
        "opSimpNac": "3",
        "regApTribSN": "1",
        "regEspTrib": "0",
        "cTribNac": "020101",
        "cNBS": "114031000",
        "tribISSQN": "1",
        "tpRetISSQN": "1",
        "CST": "00",
        "tpRetPisCofins": "0",
        "pTotTribFed": "13.45",
        "pTotTribEst": "0.00",
        "pTotTribMun": "3.83",
        "indTotTrib": None,
    }


def test_invalid_st_configuration_does_not_change_mr_and_address_is_atomic() -> None:
    mr_before, _, _ = build_dps(snapshot(), series=1, number=1, issued_at=datetime.now(UTC))
    invalid = snapshot(issuer="st")
    invalid["fiscal_rules"] = {**st_rules(), "reg_ap_trib_sn": None}
    with pytest.raises(FiscalConfigurationError):
        build_dps(invalid, series=1, number=2, issued_at=datetime.now(UTC))
    mr_after, _, _ = build_dps(snapshot(), series=1, number=3, issued_at=datetime.now(UTC))
    assert fiscal_semantics(mr_before) == fiscal_semantics(mr_after)
    full, _, _ = build_dps(snapshot(), series=1, number=4, issued_at=datetime.now(UTC))
    partial, _, _ = build_dps(
        snapshot(complete_address=False), series=1, number=5, issued_at=datetime.now(UTC)
    )
    assert etree.fromstring(full).find(f".//{{{NFSE}}}xBairro") is not None
    assert etree.fromstring(partial).find(f".//{{{NFSE}}}end") is None


def test_certificate_lookup_is_scoped_to_each_config_key() -> None:
    calls: list[dict[str, object]] = []

    class EmptyResult:
        def first(self):
            return None

    class RecordingSession:
        def execute(self, statement, params):
            del statement
            calls.append(params)
            return EmptyResult()

    for establishment, key in (("issuer-mr", "key-mr"), ("issuer-st", "key-st")):
        config = type("Config", (), {
            "establishment_id": establishment,
            "certificate_key_id": key,
            "environment": "production",
        })()
        with pytest.raises(Exception, match="Nenhum certificado A1 ativo"):
            certificate_vault._load_stored_material(RecordingSession(), config)
    assert [call["certificate_key_id"] for call in calls] == ["key-mr", "key-st"]


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
        c14n(signed_info),
        padding.PKCS1v15(),
        hashes.SHA1(),  # noqa: S303 - perfil homologado do legado
    )
    inf = root.find(f"{{{NFSE}}}infDPS")
    assert inf is not None and inf.get("Id") == dps_identifier
    expected_digest = base64.b64encode(
        hashlib.sha1(c14n(inf), usedforsecurity=False).digest()
    ).decode()
    assert signature.findtext(f".//{{{DS}}}DigestValue") == expected_digest


def test_private_document_store_rejects_path_escape(tmp_path) -> None:
    store = PrivateFilesystemDocumentStore(tmp_path / "private")
    with pytest.raises(ValueError, match="inválida"):
        store.path_for("../outside.xml")


def test_real_nfse_13_metadata_and_friendly_filenames() -> None:
    metadata = extract_authorized_nfse_metadata(AUTHORIZED_NFSE_XML)
    assert metadata.nfse_number == "13"
    assert metadata.dps_number == "13"
    assert metadata.access_key == "42091022239813375000106000000000001326090584825643"
    assert friendly_nfse_filename(
        document_type="nfse_xml",
        nfse_number=metadata.nfse_number,
        trade_name="Dom Haus",
        legal_name="Razão social não utilizada",
    ) == "NFSE_13_DOM_HAUS.xml"
    assert friendly_nfse_filename(
        document_type="danfse_pdf",
        nfse_number=metadata.nfse_number,
        trade_name=None,
        legal_name="Clínica São João Ltda.",
    ) == "NFSE_13_CLINICA_SAO_JOAO_LTDA.pdf"


def test_sefin_authorization_uses_number_and_key_from_authorized_xml() -> None:
    result = SefinGateway._authorized_result(
        {"nfseXmlGZipB64": base64.b64encode(gzip.compress(AUTHORIZED_NFSE_XML)).decode()},
        http_status=201,
        dps_id="DPS-SYNTHETIC",
    )
    assert result.status == "completed"
    assert result.nfse_number == "13"
    assert result.access_key == "42091022239813375000106000000000001326090584825643"
    assert result.documents[0].content == AUTHORIZED_NFSE_XML


def test_danfse_is_rendered_only_from_real_authorized_xml() -> None:
    pdf = render_danfse_from_authorized_xml(AUTHORIZED_NFSE_XML)
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 10_000

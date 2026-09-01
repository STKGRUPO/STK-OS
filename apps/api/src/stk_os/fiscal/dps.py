from __future__ import annotations

import re
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from lxml import etree

from stk_os.fiscal.configuration import (
    FiscalConfigurationError,
    required_text,
    validate_fiscal_rules,
)
from stk_os.fiscal.engine import FiscalDecision, calculate

NS = "http://www.sped.fazenda.gov.br/nfse"

SP_TZ = ZoneInfo("America/Sao_Paulo")


def emission_timestamp() -> str:
    """Gera o instante de emissão no fuso de São Paulo com margem segura."""
    now = datetime.now(SP_TZ) - timedelta(seconds=120)
    return now.replace(microsecond=0).isoformat()
    

def digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def q(name: str) -> str:
    return f"{{{NS}}}{name}"


_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def xml_text(value: object) -> str:
    """Normaliza texto para o validador da SEFIN (E0714).

    Remove CR, caracteres de controle e espaços repetidos. `xDescServ` aceita
    quebra de linha, mas nao aceita CR nem controle; por seguranca a quebra
    tambem e convertida em espaco simples.
    """
    text = str(value if value is not None else "")
    text = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    text = text.replace("\t", " ")
    text = _CONTROL_CHARS.sub("", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def add(parent: etree._Element, name: str, value: object) -> etree._Element:
    child = etree.SubElement(parent, q(name))
    child.text = xml_text(value)
    return child


def dps_id(snapshot: dict[str, Any], series: int, number: int) -> str:
    return (
        "DPS"
        + digits(snapshot["issuer"]["municipality_code"])
        + "2"
        + digits(snapshot["issuer"]["tax_id"])
        + f"{series:05d}"
        + f"{number:015d}"
    )


def build_dps(
    snapshot: dict[str, Any], *, series: int, number: int, issued_at: datetime
) -> tuple[bytes, str, FiscalDecision]:
    issuer = snapshot["issuer"]
    customer = snapshot["customer"]
    rules = snapshot["fiscal_rules"]
    validate_fiscal_rules(rules)
    decision = calculate(
        {"tax_regime": required_text(rules, "tax_regime"), "fiscal": rules},
        required_text(rules, "service_profile"),
        Decimal(snapshot["gross_amount"]),
    )
    identifier = dps_id(snapshot, series, number)
    root = etree.Element(q("DPS"), nsmap={None: NS}, versao="1.01")
    inf = etree.SubElement(root, q("infDPS"), Id=identifier)
    add(inf, "tpAmb", "1" if snapshot["environment"] == "production" else "2")
    add(inf, "dhEmi", emission_timestamp())
    add(inf, "verAplic", "STK-OS-Fiscal-1.0")
    add(inf, "serie", series)
    add(inf, "nDPS", number)
    add(inf, "dCompet", snapshot["competence_date"])
    add(inf, "tpEmit", "1")
    add(inf, "cLocEmi", digits(issuer["municipality_code"]))
    prest = etree.SubElement(inf, q("prest"))
    add(prest, "CNPJ", digits(issuer["tax_id"]))
    reg = etree.SubElement(prest, q("regTrib"))
    # opSimpNac vem SOMENTE do cadastro fiscal do emissor. Sem default silencioso:
    # quem valida a ausencia e validate_reg_trib(), antes de assinar.
    op_simp_nac = str(rules.get("op_simp_nac") or "").strip()
    add(reg, "opSimpNac", op_simp_nac)
    reg_ap_trib_sn = str(rules.get("reg_ap_trib_sn") or "").strip()
    # Fora de optante ME/EPP a tag nao pode existir no XML.
    if op_simp_nac == "3" and reg_ap_trib_sn:
        add(reg, "regApTribSN", reg_ap_trib_sn)
    add(reg, "regEspTrib", required_text(rules, "reg_esp_trib"))
    toma = etree.SubElement(inf, q("toma"))
    add(toma, "CNPJ", digits(customer["tax_id"]))
    add(toma, "xNome", customer["legal_name"])
    address_fields = (
        customer.get("municipality_code"),
        customer.get("postal_code"),
        customer.get("address_line"),
        customer.get("address_number"),
        customer.get("district"),
    )
    if all(str(value or "").strip() for value in address_fields):
        endereco = etree.SubElement(toma, q("end"))
        nacional = etree.SubElement(endereco, q("endNac"))
        add(nacional, "cMun", digits(customer["municipality_code"]))
        add(nacional, "CEP", digits(customer["postal_code"]))
        add(endereco, "xLgr", customer["address_line"])
        add(endereco, "nro", customer["address_number"])
        complemento = str(customer.get("address_complement") or "").strip()
        if complemento:
            add(endereco, "xCpl", complemento)
        add(endereco, "xBairro", customer["district"])
    serv = etree.SubElement(inf, q("serv"))
    loc = etree.SubElement(serv, q("locPrest"))
    add(loc, "cLocPrestacao", digits(issuer["municipality_code"]))
    codes = etree.SubElement(serv, q("cServ"))
    add(codes, "cTribNac", digits(snapshot["service_code"]))
    add(codes, "xDescServ", snapshot["service_description"])
    add(codes, "cNBS", digits(snapshot["nbs_code"]))
    valores = etree.SubElement(inf, q("valores"))
    service_values = etree.SubElement(valores, q("vServPrest"))
    add(service_values, "vServ", f"{decision.bruto:.2f}")
    trib = etree.SubElement(valores, q("trib"))
    municipal = etree.SubElement(trib, q("tribMun"))
    add(municipal, "tribISSQN", required_text(rules, "trib_issqn"))
    add(municipal, "tpRetISSQN", "2" if decision.reter_iss else "1")
    if decision.reter_iss and decision.iss > 0:
        add(municipal, "pAliq", required_text(rules, "iss_percent"))
    federal = etree.SubElement(trib, q("tribFed"))
    pcf = etree.SubElement(federal, q("piscofins"))
    add(pcf, "CST", required_text(rules, "pis_cofins_cst"))
    if decision.federal_fields_mode == "standard":
        add(pcf, "vBCPisCofins", f"{decision.bruto:.2f}")
        add(pcf, "pAliqPis", required_text(rules, "pis_percent"))
        add(pcf, "pAliqCofins", required_text(rules, "cofins_percent"))
        add(pcf, "vPis", f"{decision.pis:.2f}")
        add(pcf, "vCofins", f"{decision.cofins:.2f}")
        if decision.irrf_retido > 0:
            add(federal, "vRetIRRF", f"{decision.irrf_retido:.2f}")
        if decision.social_retido > 0:
            # Preservado do legado; o Gate A deve validar o mapeamento agregado.
            add(federal, "vRetCSLL", f"{decision.social_retido:.2f}")
    retention_type = required_text(rules, "pis_cofins_retention_type")
    if retention_type == "automatic":
        retention_type = "3" if decision.reter_social else "0"
    add(pcf, "tpRetPisCofins", retention_type)
    total = etree.SubElement(trib, q("totTrib"))
    strategy = required_text(rules, "tot_trib_strategy")
    if strategy == "percentual":
        percentages = etree.SubElement(total, q("pTotTrib"))
        add(percentages, "pTotTribFed", required_text(rules, "aprox_tributos_federal"))
        add(percentages, "pTotTribEst", required_text(rules, "aprox_tributos_estadual"))
        add(percentages, "pTotTribMun", required_text(rules, "aprox_tributos_municipal"))
    elif strategy == "simples_nacional":
        add(total, "pTotTribSN", required_text(rules, "simples_total_tax_percent"))
    else:  # proteção defensiva; validate_fiscal_rules já rejeita antes.
        raise FiscalConfigurationError("Estratégia tot_trib_strategy inválida.")
    xml_bytes = etree.tostring(root, xml_declaration=True, encoding="UTF-8")
    return xml_bytes, identifier, decision

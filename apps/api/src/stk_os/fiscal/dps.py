from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from decimal import Decimal
from typing import Any

from lxml import etree

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
    decision = calculate(
        {"tax_regime": rules.get("tax_regime", "lucro_presumido"), "fiscal": rules},
        rules.get("service_profile", "perfil_empresa"),
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
    is_simple = rules.get("tax_regime") == "simples_nacional"
    add(reg, "opSimpNac", rules.get("op_simp_nac", 3 if is_simple else 1))
    if is_simple and rules.get("reg_ap_trib_sn"):
        add(reg, "regApTribSN", rules["reg_ap_trib_sn"])
    add(reg, "regEspTrib", rules.get("reg_esp_trib", 0))
    toma = etree.SubElement(inf, q("toma"))
    add(toma, "CNPJ", digits(customer["tax_id"]))
    add(toma, "xNome", customer["legal_name"])
    endereco = etree.SubElement(toma, q("end"))
    nacional = etree.SubElement(endereco, q("endNac"))
    add(nacional, "cMun", digits(customer["municipality_code"]))
    add(nacional, "CEP", digits(customer["postal_code"]))
    add(endereco, "xLgr", customer.get("address_line") or "Nao informado")
    add(endereco, "nro", rules.get("taker_address_number", "S/N"))
    complemento = (customer.get("address_complement") or "").strip()
    if complemento:
        add(endereco, "xCpl", complemento)
    add(endereco, "xBairro", (customer.get("district") or "").strip() or "Centro")
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
    add(municipal, "tribISSQN", "1")
    add(municipal, "tpRetISSQN", "2" if decision.reter_iss else "1")
    if decision.reter_iss and decision.iss > 0:
        add(municipal, "pAliq", rules.get("iss_percent", "0.00"))
    if decision.federal_fields_mode == "standard":
        federal = etree.SubElement(trib, q("tribFed"))
        pcf = etree.SubElement(federal, q("piscofins"))
        add(pcf, "CST", "01")
        add(pcf, "vBCPisCofins", f"{decision.bruto:.2f}")
        add(pcf, "pAliqPis", rules.get("pis_percent", "0.65"))
        add(pcf, "pAliqCofins", rules.get("cofins_percent", "3.00"))
        add(pcf, "vPis", f"{decision.pis:.2f}")
        add(pcf, "vCofins", f"{decision.cofins:.2f}")
        add(pcf, "tpRetPisCofins", "3" if decision.reter_social else "0")
        if decision.irrf_retido > 0:
            add(federal, "vRetIRRF", f"{decision.irrf_retido:.2f}")
        if decision.social_retido > 0:
            # Preservado do legado; o Gate A deve validar o mapeamento agregado.
            add(federal, "vRetCSLL", f"{decision.social_retido:.2f}")
    total = etree.SubElement(trib, q("totTrib"))
    if is_simple:
        if rules.get("simples_total_tax_percent"):
            add(total, "pTotTribSN", rules["simples_total_tax_percent"])
        else:
            add(total, "indTotTrib", "0")
    else:
        percentages = etree.SubElement(total, q("pTotTrib"))
        add(percentages, "pTotTribFed", rules.get("aprox_tributos_federal", "13.45"))
        add(percentages, "pTotTribEst", rules.get("aprox_tributos_estadual", "0.00"))
        add(percentages, "pTotTribMun", rules.get("aprox_tributos_municipal", "3.83"))
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8"), identifier, decision

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


class FiscalConfigurationError(ValueError):
    """Configuração fiscal obrigatória ausente ou incoerente."""


def required_text(rules: dict[str, Any], name: str) -> str:
    value = str(rules.get(name) or "").strip()
    if not value:
        raise FiscalConfigurationError(f"Configuração fiscal sem {name}.")
    return value


def required_decimal(rules: dict[str, Any], name: str) -> Decimal:
    value = required_text(rules, name)
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise FiscalConfigurationError(f"Configuração fiscal inválida em {name}.") from error
    if parsed < 0:
        raise FiscalConfigurationError(f"Configuração fiscal inválida em {name}.")
    return parsed


def required_bool(rules: dict[str, Any], name: str) -> bool:
    value = rules.get(name)
    if type(value) is not bool:
        raise FiscalConfigurationError(f"Configuração fiscal sem booleano explícito {name}.")
    return value


def validate_fiscal_rules(rules: dict[str, Any]) -> None:
    regime = required_text(rules, "tax_regime")
    if regime not in {"lucro_presumido", "simples_nacional"}:
        raise FiscalConfigurationError("Regime fiscal não suportado nesta versão.")

    op_simp = required_text(rules, "op_simp_nac")
    expected_op = "3" if regime == "simples_nacional" else "1"
    if op_simp != expected_op:
        raise FiscalConfigurationError("tax_regime e op_simp_nac estão incoerentes.")
    reg_ap = str(rules.get("reg_ap_trib_sn") or "").strip()
    if regime == "simples_nacional" and reg_ap not in {"1", "2", "3"}:
        raise FiscalConfigurationError("Emissor do Simples sem reg_ap_trib_sn válido.")
    if regime != "simples_nacional" and reg_ap:
        raise FiscalConfigurationError("reg_ap_trib_sn só pode existir no Simples Nacional.")

    reg_esp = required_text(rules, "reg_esp_trib")
    if reg_esp not in {"0", "1", "2", "3", "4", "5", "6"}:
        raise FiscalConfigurationError("reg_esp_trib inválido.")
    required_text(rules, "service_profile")
    required_text(rules, "trib_issqn")
    required_decimal(rules, "iss_percent")
    required_bool(rules, "iss_retained_by_taker")

    cst = required_text(rules, "pis_cofins_cst")
    if len(cst) != 2 or not cst.isdigit():
        raise FiscalConfigurationError("pis_cofins_cst deve possuir dois dígitos.")
    retention_type = required_text(rules, "pis_cofins_retention_type")
    expected_retention_type = "0" if regime == "simples_nacional" else "automatic"
    if retention_type != expected_retention_type:
        raise FiscalConfigurationError(
            "pis_cofins_retention_type incoerente com o regime fiscal."
        )

    if regime == "lucro_presumido":
        for name in ("pis_percent", "cofins_percent", "csll_percent", "irrf_percent"):
            required_decimal(rules, name)
        for name in ("social_retention_applicable", "irrf_retention_applicable"):
            required_bool(rules, name)
        for name in ("social_retention_min", "irrf_retention_min"):
            required_decimal(rules, name)

    strategy = required_text(rules, "tot_trib_strategy")
    if strategy == "percentual":
        for name in (
            "aprox_tributos_federal",
            "aprox_tributos_estadual",
            "aprox_tributos_municipal",
        ):
            required_decimal(rules, name)
    elif strategy == "simples_nacional":
        if regime != "simples_nacional":
            raise FiscalConfigurationError("pTotTribSN só pode ser usado no Simples Nacional.")
        required_decimal(rules, "simples_total_tax_percent")
    else:
        raise FiscalConfigurationError("Estratégia tot_trib_strategy inválida.")


def validate_fiscal_config(config: Any) -> None:
    required = {
        "certificate_secret_ref": config.certificate_secret_ref,
        "certificate_key_id": config.certificate_key_id,
        "municipality_code": config.municipality_code,
        "service_code": config.service_code,
        "nbs_code": config.nbs_code,
    }
    missing = [name for name, value in required.items() if not str(value or "").strip()]
    if missing:
        raise FiscalConfigurationError(
            "Configuração fiscal obrigatória ausente: " + ", ".join(missing)
        )
    if not str(config.municipality_code).isdigit() or len(config.municipality_code) != 7:
        raise FiscalConfigurationError("municipality_code fiscal inválido.")
    validate_fiscal_rules(config.fiscal_rules or {})

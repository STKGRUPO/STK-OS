from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from stk_os.fiscal.configuration import (
    FiscalConfigurationError,
    required_bool,
    required_decimal,
    validate_fiscal_rules,
)

CENT = Decimal("0.01")
PROFILE_PROFESSIONAL = "servicos_profissionais"
PROFILE_NO_FEDERAL = "sem_retencoes_federais"
PROFILE_COMPANY_DEFAULT = "perfil_empresa"


def q2(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class FiscalDecision:
    bruto: Decimal
    iss: Decimal
    pis: Decimal
    cofins: Decimal
    csll: Decimal
    irrf_calculado: Decimal
    social_calculado: Decimal
    social_retido: Decimal
    irrf_retido: Decimal
    iss_retido: Decimal
    total_retido: Decimal
    liquido: Decimal
    reter_social: bool
    reter_irrf: bool
    reter_iss: bool
    social_applicable: bool
    irrf_applicable: bool
    federal_fields_mode: str
    social_reason: str
    irrf_reason: str
    iss_reason: str
    regime_reason: str

    def snapshot(self) -> dict[str, object]:
        return {
            key: str(value) if isinstance(value, Decimal) else value
            for key, value in asdict(self).items()
        }


def calculate(company: dict[str, Any], service_profile: str, bruto: Decimal) -> FiscalDecision:
    """Motor fiscal determinístico V0.2 preservado do legado validado."""
    bruto = q2(bruto)
    fiscal = company.get("fiscal", {})
    validate_fiscal_rules(fiscal)
    regime = str(company.get("tax_regime") or "")
    if regime != fiscal["tax_regime"]:
        raise FiscalConfigurationError(
            "Regime informado ao motor diverge da configuração fiscal."
        )
    iss_rate = required_decimal(fiscal, "iss_percent") / 100
    if regime == "lucro_presumido":
        pis_rate = required_decimal(fiscal, "pis_percent") / 100
        cofins_rate = required_decimal(fiscal, "cofins_percent") / 100
        csll_rate = required_decimal(fiscal, "csll_percent") / 100
        irrf_rate = required_decimal(fiscal, "irrf_percent") / 100
    else:
        pis_rate = cofins_rate = csll_rate = irrf_rate = Decimal("0")
    iss = q2(bruto * iss_rate)
    pis = q2(bruto * pis_rate)
    cofins = q2(bruto * cofins_rate)
    csll = q2(bruto * csll_rate)
    irrf_calc = q2(bruto * irrf_rate)
    social_calc = q2(pis + cofins + csll)
    iss_retained = required_bool(fiscal, "iss_retained_by_taker")
    iss_ret = iss if iss_retained else Decimal("0.00")
    iss_reason = (
        "Retido pelo tomador conforme perfil cadastrado do serviço."
        if iss_retained
        else "Não retido conforme perfil cadastrado do serviço."
    )
    if regime == "simples_nacional":
        regime_reason = "Prestador optante pelo Simples Nacional (ME/EPP)."
        pis = cofins = csll = irrf_calc = social_calc = Decimal("0.00")
        if not iss_retained:
            iss = iss_ret = Decimal("0.00")
            iss_reason = "ISS não retido; apuração no Simples Nacional conforme perfil."
        social_ret = irrf_ret = Decimal("0.00")
        social_applicable = irrf_applicable = False
        social_reason = "Não reter: optante pelo Simples Nacional, receitas próprias."
        irrf_reason = social_reason
        federal_fields_mode = "omit"
    else:
        regime_reason = f"Prestador no regime {regime.replace('_', ' ').title()}."
        enabled = service_profile != PROFILE_NO_FEDERAL
        social_applicable = enabled and required_bool(fiscal, "social_retention_applicable")
        irrf_applicable = enabled and required_bool(fiscal, "irrf_retention_applicable")
        social_threshold = required_decimal(fiscal, "social_retention_min")
        irrf_threshold = required_decimal(fiscal, "irrf_retention_min")
        social_ret = (
            social_calc if social_applicable and social_calc > social_threshold else Decimal("0.00")
        )
        irrf_ret = irrf_calc if irrf_applicable and irrf_calc > irrf_threshold else Decimal("0.00")
        social_reason = (
            "Reter contribuições sociais: valor acima do limite de dispensa."
            if social_ret
            else "Não reter contribuições sociais: inaplicável ou dentro do limite."
        )
        irrf_reason = (
            "Reter IRRF: valor acima do limite de dispensa."
            if irrf_ret
            else "Não reter IRRF: inaplicável ou dentro do limite."
        )
        federal_fields_mode = "standard"
    total_ret = q2(social_ret + irrf_ret + iss_ret)
    return FiscalDecision(
        bruto=bruto,
        iss=iss,
        pis=pis,
        cofins=cofins,
        csll=csll,
        irrf_calculado=irrf_calc,
        social_calculado=social_calc,
        social_retido=q2(social_ret),
        irrf_retido=q2(irrf_ret),
        iss_retido=q2(iss_ret),
        total_retido=total_ret,
        liquido=q2(bruto - total_ret),
        reter_social=social_ret > 0,
        reter_irrf=irrf_ret > 0,
        reter_iss=iss_ret > 0,
        social_applicable=social_applicable,
        irrf_applicable=irrf_applicable,
        federal_fields_mode=federal_fields_mode,
        social_reason=social_reason,
        irrf_reason=irrf_reason,
        iss_reason=iss_reason,
        regime_reason=regime_reason,
    )

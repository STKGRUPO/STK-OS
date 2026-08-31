"""Reserva canônica e atômica do número da DPS.

Único mecanismo autorizado a atribuir dps_number. A reserva é serializada por
linha de configuração (SELECT ... FOR UPDATE) e nunca fica abaixo do histórico
já registrado, o que cura contadores desalinhados sem intervenção manual.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from stk_os.models import FiscalEstablishmentConfig, FiscalIssuance


def highest_reserved_number(session: Session, config: FiscalEstablishmentConfig) -> int:
    """Maior dps_number já reservado para config + ambiente + série."""
    value = session.scalar(
        select(func.max(FiscalIssuance.dps_number)).where(
            FiscalIssuance.establishment_config_id == config.id,
            FiscalIssuance.environment == config.environment,
            FiscalIssuance.series == config.series,
        )
    )
    return int(value or 0)


def reserve_dps_number(session: Session, config: FiscalEstablishmentConfig) -> int:
    """Reserva o próximo número da DPS dentro da transação corrente.

    O contador é apenas um cache: a fonte de verdade é o histórico. O número
    devolvido é sempre maior que qualquer dps_number já reservado.
    """
    locked = session.scalar(
        select(FiscalEstablishmentConfig)
        .where(FiscalEstablishmentConfig.id == config.id)
        .with_for_update()
    )
    if locked is None:
        raise RuntimeError("Configuração fiscal desapareceu durante a reserva da DPS")
    historic = highest_reserved_number(session, locked)
    number = max(int(locked.next_dps_number or 1), historic + 1)
    locked.next_dps_number = number + 1
    session.add(locked)
    session.flush()
    return number

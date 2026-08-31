"""Reserva canônica e atômica do número da DPS.

Único mecanismo autorizado a atribuir dps_number. A reserva é serializada por
linha de configuração (SELECT ... FOR UPDATE) e nunca fica abaixo do histórico
já registrado, o que cura contadores desalinhados sem intervenção manual.
"""

import uuid

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


def sync_dps_sequence(session: Session, config_id: uuid.UUID) -> tuple[int, int, int]:
    """Nivela next_dps_number ao histórico, sem criar DPS e sem tocar na SEFIN.

    Retorna (valor_anterior, valor_novo, maior_dps_number). Nunca reduz o
    contador: aplica next = max(next, MAX(dps_number) + 1) sob FOR UPDATE.
    """
    locked = session.scalar(
        select(FiscalEstablishmentConfig)
        .where(FiscalEstablishmentConfig.id == config_id)
        .with_for_update()
    )
    if locked is None:
        raise RuntimeError("Configuração fiscal não encontrada para sincronizar a sequência")
    historic = highest_reserved_number(session, locked)
    previous = int(locked.next_dps_number or 1)
    updated = max(previous, historic + 1)
    locked.next_dps_number = updated
    session.add(locked)
    session.flush()
    return previous, updated, historic
    

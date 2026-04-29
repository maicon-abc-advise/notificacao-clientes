"""Atualização de ``engajamento_usuarios`` por canal (e-mail vs SMS).

Cada canal tem estado e timestamp próprios; ``engajamento_atualizado_em`` reflete qualquer alteração na linha.
"""

from __future__ import annotations

import logging
import uuid

import asyncpg

from app.reenvio.servicos.engajamento_estado import EngajamentoEmailEstado, EngajamentoSmsEstado

_log = logging.getLogger(__name__)


def parse_usuario_id(val: str | None) -> uuid.UUID | None:
    if not val or not str(val).strip():
        return None
    try:
        return uuid.UUID(str(val).strip())
    except ValueError:
        return None


async def tocar_engajamento_email(
    pool: asyncpg.Pool,
    usuario_id: uuid.UUID | None,
    estado: EngajamentoEmailEstado,
) -> None:
    """Upsert só do ramo e-mail; ignora se ``usuario_id`` for nulo."""
    if usuario_id is None:
        return
    est = estado.value[:64]
    await pool.execute(
        """
        INSERT INTO public.engajamento_usuarios (
            usuario_id, engajamento_email, engajamento_email_atualizado_em, engajamento_atualizado_em
        )
        VALUES ($1, $2, now(), now())
        ON CONFLICT (usuario_id) DO UPDATE SET
            engajamento_email = EXCLUDED.engajamento_email,
            engajamento_email_atualizado_em = now(),
            engajamento_atualizado_em = now()
        """,
        usuario_id,
        est,
    )
    _log.debug("Engajamento e-mail usuario_id=%s estado=%s", usuario_id, est)


async def tocar_engajamento_sms(
    pool: asyncpg.Pool,
    usuario_id: uuid.UUID | None,
    estado: EngajamentoSmsEstado,
) -> None:
    """Upsert só do ramo SMS; ignora se ``usuario_id`` for nulo."""
    if usuario_id is None:
        return
    est = estado.value[:64]
    await pool.execute(
        """
        INSERT INTO public.engajamento_usuarios (
            usuario_id, engajamento_sms, engajamento_sms_atualizado_em, engajamento_atualizado_em
        )
        VALUES ($1, $2, now(), now())
        ON CONFLICT (usuario_id) DO UPDATE SET
            engajamento_sms = EXCLUDED.engajamento_sms,
            engajamento_sms_atualizado_em = now(),
            engajamento_atualizado_em = now()
        """,
        usuario_id,
        est,
    )
    _log.debug("Engajamento SMS usuario_id=%s estado=%s", usuario_id, est)


async def definir_recebe_email(
    pool: asyncpg.Pool,
    usuario_id: uuid.UUID | None,
    recebe: bool,
) -> None:
    """Atualiza ``recebe_email``; ignora se ``usuario_id`` for nulo."""
    if usuario_id is None:
        return
    await pool.execute(
        """
        INSERT INTO public.engajamento_usuarios (
            usuario_id, recebe_email, engajamento_atualizado_em
        )
        VALUES ($1, $2, now())
        ON CONFLICT (usuario_id) DO UPDATE SET
            recebe_email = EXCLUDED.recebe_email,
            engajamento_atualizado_em = now()
        """,
        usuario_id,
        recebe,
    )
    _log.debug("recebe_email=%s usuario_id=%s", recebe, usuario_id)

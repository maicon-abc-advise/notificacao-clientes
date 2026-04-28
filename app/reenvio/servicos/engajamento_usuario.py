"""Atualização de ``engajamento_usuarios`` em qualquer evento de e-mail ou SMS (API ou webhook).

Valores de estado: ``EngajamentoEstado``; ``engajamento_atualizado_em`` é sempre atualizado.
"""

from __future__ import annotations

import logging
import uuid

import asyncpg

from app.reenvio.servicos.engajamento_estado import EngajamentoEstado

_log = logging.getLogger(__name__)


def parse_usuario_id(val: str | None) -> uuid.UUID | None:
    if not val or not str(val).strip():
        return None
    try:
        return uuid.UUID(str(val).strip())
    except ValueError:
        return None


async def tocar_engajamento(
    pool: asyncpg.Pool,
    usuario_id: uuid.UUID | None,
    estado: EngajamentoEstado,
) -> None:
    """Upsert em ``engajamento_usuarios``; ignora se ``usuario_id`` for nulo."""
    if usuario_id is None:
        return
    est = estado.value[:64]
    await pool.execute(
        """
        INSERT INTO public.engajamento_usuarios (
            usuario_id, engajamento_estado, engajamento_atualizado_em
        )
        VALUES ($1, $2, now())
        ON CONFLICT (usuario_id) DO UPDATE SET
            engajamento_estado = EXCLUDED.engajamento_estado,
            engajamento_atualizado_em = now()
        """,
        usuario_id,
        est,
    )
    _log.debug("Engajamento atualizado usuario_id=%s estado=%s", usuario_id, est)

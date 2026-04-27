"""Atualização de ``engajamento_usuarios`` em qualquer evento de e-mail ou SMS (API ou webhook).

O campo ``engajamento_estado`` guarda um rótulo curto do último evento (ex.: ``email_lido``,
``sms_entregue``). Ajuste os textos conforme o produto; ``engajamento_atualizado_em`` é sempre atualizado.
"""

from __future__ import annotations

import logging
import uuid

import asyncpg

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
    estado: str,
) -> None:
    """Upsert em ``engajamento_usuarios``; ignora se ``usuario_id`` for nulo."""
    if usuario_id is None:
        return
    est = (estado or "ativo")[:64]
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

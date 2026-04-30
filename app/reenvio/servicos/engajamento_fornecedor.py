"""Atualização de ``engajamento_fornecedores`` por canal (e-mail vs SMS)."""

from __future__ import annotations

import logging
import uuid

import asyncpg

from app.reenvio.servicos.engajamento_estado import EngajamentoEmailEstado, EngajamentoSmsEstado

_log = logging.getLogger(__name__)


def parse_fornecedor_id(val: str | None) -> uuid.UUID | None:
    if not val or not str(val).strip():
        return None
    try:
        return uuid.UUID(str(val).strip())
    except ValueError:
        return None


async def tocar_engajamento_email(
    pool: asyncpg.Pool,
    fornecedor_id: uuid.UUID | None,
    estado: EngajamentoEmailEstado,
) -> None:
    """Upsert só do ramo e-mail; ignora se ``fornecedor_id`` for nulo."""
    if fornecedor_id is None:
        return
    est = estado.value
    await pool.execute(
        """
        INSERT INTO public.engajamento_fornecedores (
            fornecedor_id, engajamento_email, engajamento_email_atualizado_em, engajamento_atualizado_em
        )
        VALUES ($1, $2, now(), now())
        ON CONFLICT (fornecedor_id) DO UPDATE SET
            engajamento_email = EXCLUDED.engajamento_email,
            engajamento_email_atualizado_em = now(),
            engajamento_atualizado_em = now()
        """,
        fornecedor_id,
        est,
    )
    _log.debug("Engajamento e-mail fornecedor_id=%s estado=%s", fornecedor_id, est)


async def tocar_engajamento_sms(
    pool: asyncpg.Pool,
    fornecedor_id: uuid.UUID | None,
    estado: EngajamentoSmsEstado,
) -> None:
    """Upsert só do ramo SMS; ignora se ``fornecedor_id`` for nulo."""
    if fornecedor_id is None:
        return
    est = estado.value
    await pool.execute(
        """
        INSERT INTO public.engajamento_fornecedores (
            fornecedor_id, engajamento_sms, engajamento_sms_atualizado_em, engajamento_atualizado_em
        )
        VALUES ($1, $2, now(), now())
        ON CONFLICT (fornecedor_id) DO UPDATE SET
            engajamento_sms = EXCLUDED.engajamento_sms,
            engajamento_sms_atualizado_em = now(),
            engajamento_atualizado_em = now()
        """,
        fornecedor_id,
        est,
    )
    _log.debug("Engajamento SMS fornecedor_id=%s estado=%s", fornecedor_id, est)


async def definir_recebe_email(
    pool: asyncpg.Pool,
    fornecedor_id: uuid.UUID | None,
    recebe: bool,
) -> None:
    """Atualiza ``recebe_email``; ignora se ``fornecedor_id`` for nulo."""
    if fornecedor_id is None:
        return
    await pool.execute(
        """
        INSERT INTO public.engajamento_fornecedores (
            fornecedor_id, recebe_email, engajamento_atualizado_em
        )
        VALUES ($1, $2, now())
        ON CONFLICT (fornecedor_id) DO UPDATE SET
            recebe_email = EXCLUDED.recebe_email,
            engajamento_atualizado_em = now()
        """,
        fornecedor_id,
        recebe,
    )
    _log.debug("recebe_email=%s fornecedor_id=%s", recebe, fornecedor_id)

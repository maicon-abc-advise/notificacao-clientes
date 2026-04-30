"""Persistência de ``public.sms_enviados`` — ligada ao envio na API de mensageria."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

import asyncpg


async def buscar_por_id_externo(pool: asyncpg.Pool, id_externo: str) -> asyncpg.Record | None:
    return await pool.fetchrow(
        """
        SELECT id_externo, id_mensagem_zenvia, telefone, tipo_template, contexto,
               remetente, fornecedor_id, status_ultimo
        FROM public.sms_enviados
        WHERE id_externo = $1
        LIMIT 1
        """,
        id_externo,
    )


async def inserir_ou_atualizar_apos_envio_api(
    pool: asyncpg.Pool,
    *,
    id_externo: str,
    telefone: str,
    tipo_template: str,
    contexto: dict[str, Any],
    remetente: str | None,
    id_mensagem_zenvia: str,
    fornecedor_id: uuid.UUID | None,
) -> None:
    """Chamado após ``POST /v1/mensagens/sms`` com sucesso (fila Redis já removida)."""
    await pool.execute(
        """
        INSERT INTO public.sms_enviados (
            id_externo, telefone, tipo_template, contexto, remetente,
            id_mensagem_zenvia, fornecedor_id, status_ultimo
        )
        VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, 'processando')
        ON CONFLICT (id_externo) DO UPDATE SET
            id_mensagem_zenvia = EXCLUDED.id_mensagem_zenvia,
            telefone = EXCLUDED.telefone,
            tipo_template = EXCLUDED.tipo_template,
            contexto = EXCLUDED.contexto,
            remetente = EXCLUDED.remetente,
            fornecedor_id = COALESCE(EXCLUDED.fornecedor_id, public.sms_enviados.fornecedor_id),
            status_ultimo = 'processando',
            atualizado_em = now()
        """,
        id_externo,
        telefone,
        tipo_template,
        json.dumps(contexto),
        remetente,
        id_mensagem_zenvia,
        fornecedor_id,
    )


async def buscar_por_id_mensagem_zenvia(
    pool: asyncpg.Pool, id_mensagem: str
) -> asyncpg.Record | None:
    return await pool.fetchrow(
        """
        SELECT id, id_externo, id_mensagem_zenvia, telefone, tipo_template, contexto,
               remetente, fornecedor_id, status_ultimo, motivo_ultimo_evento,
               tentativas_reprocessar, proxima_tentativa_em
        FROM public.sms_enviados
        WHERE id_mensagem_zenvia = $1
        LIMIT 1
        """,
        id_mensagem,
    )


async def atualizar_status_por_id_interno(
    pool: asyncpg.Pool,
    *,
    id_interno: uuid.UUID,
    status_ultimo: str,
    motivo: str | None,
    tentativas: int | None = None,
    proxima_tentativa_em: datetime | None = None,
) -> None:
    await pool.execute(
        """
        UPDATE public.sms_enviados
        SET status_ultimo = $2,
            motivo_ultimo_evento = $3,
            tentativas_reprocessar = COALESCE($4, tentativas_reprocessar),
            proxima_tentativa_em = COALESCE($5, proxima_tentativa_em),
            atualizado_em = now()
        WHERE id = $1
        """,
        id_interno,
        status_ultimo,
        motivo,
        tentativas,
        proxima_tentativa_em,
    )

"""Persistência de ``public.emails_enviados`` — ligada ao envio na API de mensageria."""

from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg


async def buscar_por_id_externo(pool: asyncpg.Pool, id_externo: str) -> asyncpg.Record | None:
    return await pool.fetchrow(
        """
        SELECT id_externo, id_mensagem_zenvia, email_destinatario, tipo_template, contexto,
               remetente, telefone_sms_fallback, fornecedor_id, status_ultimo
        FROM public.emails_enviados
        WHERE id_externo = $1
        LIMIT 1
        """,
        id_externo,
    )


async def atualizar_status_por_id_mensagem_zenvia(
    pool: asyncpg.Pool, *, id_mensagem_zenvia: str, status_ultimo: str
) -> None:
    """Atualiza ``status_ultimo`` (webhook / pós-envio). Silencioso se não houver linha."""
    await pool.execute(
        """
        UPDATE public.emails_enviados
        SET status_ultimo = $2, atualizado_em = now()
        WHERE id_mensagem_zenvia = $1
        """,
        id_mensagem_zenvia,
        status_ultimo,
    )


async def inserir_ou_atualizar_apos_envio_api(
    pool: asyncpg.Pool,
    *,
    id_externo: str,
    email_destinatario: str,
    tipo_template: str,
    contexto: dict[str, Any],
    remetente: str | None,
    telefone_sms_fallback: str | None,
    id_mensagem_zenvia: str,
    fornecedor_id: uuid.UUID | None,
) -> None:
    """Chamado após ``POST /v1/mensagens/email`` com sucesso."""
    await pool.execute(
        """
        INSERT INTO public.emails_enviados (
            id_externo, email_destinatario, tipo_template, contexto, remetente,
            telefone_sms_fallback, id_mensagem_zenvia, fornecedor_id, status_ultimo
        )
        VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, 'processando')
        ON CONFLICT (id_externo) DO UPDATE SET
            id_mensagem_zenvia = EXCLUDED.id_mensagem_zenvia,
            email_destinatario = EXCLUDED.email_destinatario,
            tipo_template = EXCLUDED.tipo_template,
            contexto = EXCLUDED.contexto,
            remetente = EXCLUDED.remetente,
            telefone_sms_fallback = COALESCE(
                EXCLUDED.telefone_sms_fallback,
                public.emails_enviados.telefone_sms_fallback
            ),
            fornecedor_id = COALESCE(EXCLUDED.fornecedor_id, public.emails_enviados.fornecedor_id),
            status_ultimo = 'processando',
            atualizado_em = now()
        """,
        id_externo,
        email_destinatario,
        tipo_template,
        json.dumps(contexto),
        remetente,
        telefone_sms_fallback,
        id_mensagem_zenvia,
        fornecedor_id,
    )

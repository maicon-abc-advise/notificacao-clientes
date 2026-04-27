"""Persistência de ``public.emails_enviados`` — ligada ao envio na API de mensageria."""

from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg


async def inserir_ou_atualizar_apos_envio_api(
    pool: asyncpg.Pool,
    *,
    external_id: str,
    email_destinatario: str,
    tipo_template: str,
    contexto: dict[str, Any],
    remetente: str | None,
    telefone_sms_fallback: str | None,
    id_mensagem_zenvia: str,
    usuario_id: uuid.UUID | None,
) -> None:
    """Chamado após ``POST /v1/mensagens/email`` com sucesso."""
    await pool.execute(
        """
        INSERT INTO public.emails_enviados (
            external_id, email_destinatario, tipo_template, contexto, remetente,
            telefone_sms_fallback, id_mensagem_zenvia, usuario_id, status_ultimo
        )
        VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, 'processando')
        ON CONFLICT (external_id) DO UPDATE SET
            id_mensagem_zenvia = EXCLUDED.id_mensagem_zenvia,
            email_destinatario = EXCLUDED.email_destinatario,
            tipo_template = EXCLUDED.tipo_template,
            contexto = EXCLUDED.contexto,
            remetente = EXCLUDED.remetente,
            telefone_sms_fallback = COALESCE(
                EXCLUDED.telefone_sms_fallback,
                public.emails_enviados.telefone_sms_fallback
            ),
            usuario_id = COALESCE(EXCLUDED.usuario_id, public.emails_enviados.usuario_id),
            status_ultimo = 'processando',
            atualizado_em = now()
        """,
        external_id,
        email_destinatario,
        tipo_template,
        json.dumps(contexto),
        remetente,
        telefone_sms_fallback,
        id_mensagem_zenvia,
        usuario_id,
    )

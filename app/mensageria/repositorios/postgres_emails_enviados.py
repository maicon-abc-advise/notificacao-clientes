"""Persistência de emails_enviados — ligada ao envio na API de mensageria."""

from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg

from app.config.postgres_identificadores import obter_identificadores_postgres


async def buscar_enviados_por_ids_externos(
    pool: asyncpg.Pool, ids_externos: list[str]
) -> list[asyncpg.Record]:
    """Retorna linhas de ``emails_enviados`` com ``id_mensagem_zenvia`` preenchido."""
    if not ids_externos:
        return []
    p = obter_identificadores_postgres()
    te = p.qual("emails_enviados")
    return await pool.fetch(
        f"""
        SELECT id_externo, id_mensagem_zenvia, cnpj_basico
        FROM {te}
        WHERE id_externo = ANY($1::text[])
          AND id_mensagem_zenvia IS NOT NULL
        """,
        ids_externos,
    )


async def buscar_por_id_externo(pool: asyncpg.Pool, id_externo: str) -> asyncpg.Record | None:
    p = obter_identificadores_postgres()
    te = p.qual("emails_enviados")
    cf = p.col_fornecedor_id
    return await pool.fetchrow(
        f"""
        SELECT id_externo, id_mensagem_zenvia, email_destinatario, tipo_template, contexto,
               remetente, {cf}, cnpj_basico, status_ultimo
        FROM {te}
        WHERE id_externo = $1
        LIMIT 1
        """,
        id_externo,
    )


async def atualizar_status_por_id_externo(
    pool: asyncpg.Pool, *, id_externo: str, status_ultimo: str
) -> None:
    p = obter_identificadores_postgres()
    te = p.qual("emails_enviados")
    await pool.execute(
        f"""
        UPDATE {te}
        SET status_ultimo = $2, atualizado_em = now()
        WHERE id_externo = $1
        """,
        id_externo,
        status_ultimo,
    )


async def buscar_status_por_id_mensagem_zenvia(
    pool: asyncpg.Pool, *, id_mensagem_zenvia: str
) -> str | None:
    p = obter_identificadores_postgres()
    te = p.qual("emails_enviados")
    row = await pool.fetchval(
        f"SELECT status_ultimo FROM {te} WHERE id_mensagem_zenvia = $1 LIMIT 1",
        id_mensagem_zenvia,
    )
    return str(row).strip() if row else None


async def atualizar_status_por_id_mensagem_zenvia(
    pool: asyncpg.Pool, *, id_mensagem_zenvia: str, status_ultimo: str
) -> None:
    """Atualiza ``status_ultimo`` (webhook / pós-envio). Silencioso se não houver linha."""
    p = obter_identificadores_postgres()
    te = p.qual("emails_enviados")
    await pool.execute(
        f"""
        UPDATE {te}
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
    id_mensagem_zenvia: str,
    fornecedor_id: uuid.UUID | None,
    cnpj_basico: str | None,
) -> None:
    """Chamado após ``POST /v1/mensagens/email`` com sucesso."""
    p = obter_identificadores_postgres()
    te = p.qual("emails_enviados")
    cf = p.col_fornecedor_id
    await pool.execute(
        f"""
        INSERT INTO {te} (
            id_externo, email_destinatario, tipo_template, contexto, remetente,
            id_mensagem_zenvia, {cf}, cnpj_basico, status_ultimo
        )
        VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, 'processando')
        ON CONFLICT (id_externo) DO UPDATE SET
            id_mensagem_zenvia = EXCLUDED.id_mensagem_zenvia,
            email_destinatario = EXCLUDED.email_destinatario,
            tipo_template = EXCLUDED.tipo_template,
            contexto = EXCLUDED.contexto,
            remetente = EXCLUDED.remetente,
            {cf} = COALESCE(EXCLUDED.{cf}, {te}.{cf}),
            cnpj_basico = COALESCE(EXCLUDED.cnpj_basico, {te}.cnpj_basico),
            status_ultimo = 'processando',
            atualizado_em = now()
        """,
        id_externo,
        email_destinatario,
        tipo_template,
        json.dumps(contexto),
        remetente,
        id_mensagem_zenvia,
        fornecedor_id,
        cnpj_basico,
    )

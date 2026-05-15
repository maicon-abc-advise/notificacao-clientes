"""Persistência de sms_enviados — ligada ao envio na API de mensageria."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

import asyncpg

from app.config.postgres_identificadores import obter_identificadores_postgres


async def buscar_por_id_externo(pool: asyncpg.Pool, id_externo: str) -> asyncpg.Record | None:
    p = obter_identificadores_postgres()
    ts = p.qual("sms_enviados")
    cf = p.col_fornecedor_id
    return await pool.fetchrow(
        f"""
        SELECT id_externo, id_mensagem_zenvia, telefone, tipo_template, contexto,
               remetente, {cf}, cnpj_basico, status_ultimo, motivo_ultimo_evento
        FROM {ts}
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
    cnpj_basico: str | None,
) -> None:
    """Chamado após ``POST /v1/mensagens/sms`` com sucesso (fila Redis já removida)."""
    p = obter_identificadores_postgres()
    ts = p.qual("sms_enviados")
    cf = p.col_fornecedor_id
    await pool.execute(
        f"""
        INSERT INTO {ts} (
            id_externo, telefone, tipo_template, contexto, remetente,
            id_mensagem_zenvia, {cf}, cnpj_basico, status_ultimo
        )
        VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, 'processando')
        ON CONFLICT (id_externo) DO UPDATE SET
            id_mensagem_zenvia = EXCLUDED.id_mensagem_zenvia,
            telefone = EXCLUDED.telefone,
            tipo_template = EXCLUDED.tipo_template,
            contexto = EXCLUDED.contexto,
            remetente = EXCLUDED.remetente,
            {cf} = COALESCE(EXCLUDED.{cf}, {ts}.{cf}),
            cnpj_basico = COALESCE(EXCLUDED.cnpj_basico, {ts}.cnpj_basico),
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
        cnpj_basico,
    )


async def inserir_ou_atualizar_falha_validacao_telefone_sms(
    pool: asyncpg.Pool,
    *,
    id_externo: str,
    telefone: str,
    tipo_template: str,
    contexto: dict[str, Any],
    remetente: str | None,
    fornecedor_id: uuid.UUID | None,
    cnpj_basico: str | None,
    motivo: str,
) -> None:
    """Registo de falha local (sem chamada ao provedor): ``id_mensagem_zenvia`` nulo, status definitivo."""
    p = obter_identificadores_postgres()
    ts = p.qual("sms_enviados")
    cf = p.col_fornecedor_id
    await pool.execute(
        f"""
        INSERT INTO {ts} (
            id_externo, telefone, tipo_template, contexto, remetente,
            id_mensagem_zenvia, {cf}, cnpj_basico, status_ultimo, motivo_ultimo_evento
        )
        VALUES ($1, $2, $3, $4::jsonb, $5, NULL, $6, $7, 'falha_definitiva', $8)
        ON CONFLICT (id_externo) DO UPDATE SET
            telefone = EXCLUDED.telefone,
            tipo_template = EXCLUDED.tipo_template,
            contexto = EXCLUDED.contexto,
            remetente = EXCLUDED.remetente,
            id_mensagem_zenvia = NULL,
            {cf} = COALESCE(EXCLUDED.{cf}, {ts}.{cf}),
            cnpj_basico = COALESCE(EXCLUDED.cnpj_basico, {ts}.cnpj_basico),
            status_ultimo = 'falha_definitiva',
            motivo_ultimo_evento = EXCLUDED.motivo_ultimo_evento,
            atualizado_em = now()
        """,
        id_externo,
        telefone,
        tipo_template,
        json.dumps(contexto),
        remetente,
        fornecedor_id,
        cnpj_basico,
        motivo,
    )


async def buscar_por_id_mensagem_zenvia(
    pool: asyncpg.Pool, id_mensagem: str
) -> asyncpg.Record | None:
    p = obter_identificadores_postgres()
    ts = p.qual("sms_enviados")
    cf = p.col_fornecedor_id
    return await pool.fetchrow(
        f"""
        SELECT id, id_externo, id_mensagem_zenvia, telefone, tipo_template, contexto,
               remetente, {cf}, cnpj_basico, status_ultimo, motivo_ultimo_evento,
               tentativas_reprocessar, proxima_tentativa_em
        FROM {ts}
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
    p = obter_identificadores_postgres()
    ts = p.qual("sms_enviados")
    await pool.execute(
        f"""
        UPDATE {ts}
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

"""Persistência de ``ligacoes_enviadas`` — histórico de ligações de voz."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

import asyncpg

from app.config.postgres_identificadores import obter_identificadores_postgres


def _tabela() -> str:
    return obter_identificadores_postgres().qual("ligacoes_enviadas")


def _col_fornecedor() -> str:
    return obter_identificadores_postgres().col_fornecedor_id


async def buscar_por_id_externo(pool: asyncpg.Pool, id_externo: str) -> asyncpg.Record | None:
    ts = _tabela()
    cf = _col_fornecedor()
    return await pool.fetchrow(
        f"""
        SELECT id, id_externo, id_chamada_vapi, telefone, cnpj_basico, {cf},
               quantidade_buscas, uf_buscada, segmento_buscado, status_ultimo,
               motivo_encerramento, transcricao, url_gravacao, duracao_segundos,
               iniciado_em, encerrado_em, nota_satisfacao, vai_cadastrar, analise_json,
               criado_em, atualizado_em
        FROM {ts}
        WHERE id_externo = $1
        LIMIT 1
        """,
        id_externo,
    )


async def buscar_por_id_chamada_vapi(pool: asyncpg.Pool, id_chamada_vapi: str) -> asyncpg.Record | None:
    ts = _tabela()
    cf = _col_fornecedor()
    return await pool.fetchrow(
        f"""
        SELECT id, id_externo, id_chamada_vapi, telefone, cnpj_basico, {cf},
               quantidade_buscas, uf_buscada, segmento_buscado, status_ultimo,
               motivo_encerramento, transcricao, url_gravacao, duracao_segundos,
               iniciado_em, encerrado_em, nota_satisfacao, vai_cadastrar, analise_json,
               criado_em, atualizado_em
        FROM {ts}
        WHERE id_chamada_vapi = $1
        LIMIT 1
        """,
        id_chamada_vapi,
    )


async def inserir_apos_disparo(
    pool: asyncpg.Pool,
    *,
    id_externo: str,
    id_chamada_vapi: str,
    telefone: str,
    cnpj_basico: str | None,
    fornecedor_id: uuid.UUID | None,
    quantidade_buscas: int | None,
    uf_buscada: str | None,
    segmento_buscado: str | None,
) -> None:
    ts = _tabela()
    cf = _col_fornecedor()
    await pool.execute(
        f"""
        INSERT INTO {ts} (
            id_externo, id_chamada_vapi, telefone, cnpj_basico, {cf},
            quantidade_buscas, uf_buscada, segmento_buscado, status_ultimo
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'disparado')
        ON CONFLICT (id_externo) DO UPDATE SET
            id_chamada_vapi = EXCLUDED.id_chamada_vapi,
            telefone = EXCLUDED.telefone,
            cnpj_basico = COALESCE(EXCLUDED.cnpj_basico, {ts}.cnpj_basico),
            {cf} = COALESCE(EXCLUDED.{cf}, {ts}.{cf}),
            quantidade_buscas = COALESCE(EXCLUDED.quantidade_buscas, {ts}.quantidade_buscas),
            uf_buscada = COALESCE(EXCLUDED.uf_buscada, {ts}.uf_buscada),
            segmento_buscado = COALESCE(EXCLUDED.segmento_buscado, {ts}.segmento_buscado),
            status_ultimo = 'disparado',
            atualizado_em = now()
        """,
        id_externo,
        id_chamada_vapi,
        telefone,
        cnpj_basico,
        fornecedor_id,
        quantidade_buscas,
        uf_buscada,
        segmento_buscado,
    )


async def atualizar_status_intermediario(
    pool: asyncpg.Pool,
    *,
    registro_id: uuid.UUID,
    status_ultimo: str,
) -> None:
    ts = _tabela()
    await pool.execute(
        f"""
        UPDATE {ts}
        SET status_ultimo = $2, atualizado_em = now()
        WHERE id = $1
        """,
        registro_id,
        status_ultimo,
    )


async def atualizar_fim_chamada(
    pool: asyncpg.Pool,
    *,
    registro_id: uuid.UUID,
    status_ultimo: str,
    motivo_encerramento: str | None,
    transcricao: str | None,
    url_gravacao: str | None,
    duracao_segundos: int | None,
    iniciado_em: datetime | None,
    encerrado_em: datetime | None,
    nota_satisfacao: int | None,
    vai_cadastrar: bool | None,
    analise_json: dict[str, Any],
) -> None:
    ts = _tabela()
    await pool.execute(
        f"""
        UPDATE {ts}
        SET status_ultimo = $2,
            motivo_encerramento = $3,
            transcricao = COALESCE($4, transcricao),
            url_gravacao = COALESCE($5, url_gravacao),
            duracao_segundos = COALESCE($6, duracao_segundos),
            iniciado_em = COALESCE($7, iniciado_em),
            encerrado_em = COALESCE($8, encerrado_em),
            nota_satisfacao = COALESCE($9, nota_satisfacao),
            vai_cadastrar = COALESCE($10, vai_cadastrar),
            analise_json = $11::jsonb,
            atualizado_em = now()
        WHERE id = $1
        """,
        registro_id,
        status_ultimo,
        motivo_encerramento,
        transcricao,
        url_gravacao,
        duracao_segundos,
        iniciado_em,
        encerrado_em,
        nota_satisfacao,
        vai_cadastrar,
        json.dumps(analise_json),
    )

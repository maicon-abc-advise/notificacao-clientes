"""Consultas mínimas a fornecedores na borda da mensageria."""

from __future__ import annotations

import uuid

import asyncpg

from app.config.postgres_identificadores import obter_identificadores_postgres


async def fornecedor_id_existe(pool: asyncpg.Pool, fornecedor_id: uuid.UUID) -> bool:
    p = obter_identificadores_postgres()
    t = p.qual("fornecedores")
    cf = p.col_fornecedor_id
    return await pool.fetchval(
        f"SELECT EXISTS (SELECT 1 FROM {t} WHERE {cf} = $1)",
        fornecedor_id,
    )


async def listar_fornecedores_diagnostico(
    pool: asyncpg.Pool,
    *,
    limite: int,
) -> list[dict[str, object]]:
    """SELECT somente leitura; nomes de tabela/coluna vêm de ``postgres_identificadores``."""
    p = obter_identificadores_postgres()
    t = p.qual("fornecedores")
    cf = p.col_fornecedor_id
    rows = await pool.fetch(
        f"SELECT * FROM {t} ORDER BY {cf} ASC LIMIT $1",
        limite,
    )
    return [dict(r) for r in rows]

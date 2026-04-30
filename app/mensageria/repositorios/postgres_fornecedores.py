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

"""Consultas mínimas a ``public.fornecedores`` na borda da mensageria."""

from __future__ import annotations

import uuid

import asyncpg


async def fornecedor_id_existe(pool: asyncpg.Pool, fornecedor_id: uuid.UUID) -> bool:
    v = await pool.fetchval(
        "SELECT EXISTS (SELECT 1 FROM public.fornecedores WHERE fornecedor_id = $1)",
        fornecedor_id,
    )
    return bool(v)

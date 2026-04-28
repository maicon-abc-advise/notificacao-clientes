from __future__ import annotations

import uuid

import asyncpg

from app.orquestracao.excecoes import ConsultaNaoEncontradaError


async def buscar_por_id(pool: asyncpg.Pool, id_consulta: uuid.UUID) -> asyncpg.Record:
    row = await pool.fetchrow(
        """
        SELECT id, created_at, status, parametros, resultados
        FROM public.consultas
        WHERE id = $1
        """,
        id_consulta,
    )
    if row is None:
        raise ConsultaNaoEncontradaError(str(id_consulta))
    return row

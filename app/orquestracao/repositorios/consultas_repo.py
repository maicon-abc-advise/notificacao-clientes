from __future__ import annotations

import uuid

import asyncpg

from app.config.postgres_identificadores import obter_identificadores_postgres
from app.orquestracao.excecoes import ConsultaNaoEncontradaError


async def buscar_por_id(pool: asyncpg.Pool, id_consulta: uuid.UUID) -> asyncpg.Record:
    p = obter_identificadores_postgres()
    t = p.qual("consultas")
    row = await pool.fetchrow(
        f"""
        SELECT id, created_at, status, parametros, resultados
        FROM {t}
        WHERE id = $1
        """,
        id_consulta,
    )
    if row is None:
        raise ConsultaNaoEncontradaError(str(id_consulta))
    return row

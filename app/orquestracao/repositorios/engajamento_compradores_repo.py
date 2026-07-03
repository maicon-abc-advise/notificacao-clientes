from __future__ import annotations

import uuid

import asyncpg

from app.config.postgres_identificadores import obter_identificadores_postgres


async def upsert_apos_envio_sms(
    pool: asyncpg.Pool,
    *,
    telefone: str,
    comprador_id: uuid.UUID,
    primeira_consulta_sem_cadastro: bool,
) -> None:
    p = obter_identificadores_postgres()
    t = p.qual("engajamento_compradores")
    await pool.execute(
        f"""
        INSERT INTO {t} (
            telefone, comprador_id, primeira_consulta_sem_cadastro, converteu,
            criado_em, atualizado_em
        )
        VALUES ($1, $2, $3, false, now(), now())
        ON CONFLICT (telefone) DO UPDATE SET
            comprador_id = COALESCE(EXCLUDED.comprador_id, {t}.comprador_id),
            atualizado_em = now()
        """,
        telefone,
        comprador_id,
        primeira_consulta_sem_cadastro,
    )

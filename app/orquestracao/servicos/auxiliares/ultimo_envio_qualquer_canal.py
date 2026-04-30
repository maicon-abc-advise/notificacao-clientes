from __future__ import annotations

import uuid
from datetime import datetime

import asyncpg

from app.config.postgres_identificadores import obter_identificadores_postgres


async def obter_ultimo_envio_em(
    pool: asyncpg.Pool,
    fornecedor_id: uuid.UUID | None,
) -> datetime | None:
    if fornecedor_id is None:
        return None
    p = obter_identificadores_postgres()
    te = p.qual("emails_enviados")
    ts = p.qual("sms_enviados")
    cf = p.col_fornecedor_id
    max_email = await pool.fetchval(
        f"SELECT MAX(criado_em) FROM {te} WHERE {cf} = $1",
        fornecedor_id,
    )
    max_sms = await pool.fetchval(
        f"SELECT MAX(criado_em) FROM {ts} WHERE {cf} = $1",
        fornecedor_id,
    )
    candidatos = [t for t in (max_email, max_sms) if t is not None]
    return max(candidatos) if candidatos else None

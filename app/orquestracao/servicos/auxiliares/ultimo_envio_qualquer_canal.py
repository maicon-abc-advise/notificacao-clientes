from __future__ import annotations

import uuid
from datetime import datetime

import asyncpg


async def obter_ultimo_envio_em(
    pool: asyncpg.Pool,
    usuario_id: uuid.UUID | None,
) -> datetime | None:
    if usuario_id is None:
        return None
    max_email = await pool.fetchval(
        "SELECT MAX(criado_em) FROM public.emails_enviados WHERE usuario_id = $1",
        usuario_id,
    )
    max_sms = await pool.fetchval(
        "SELECT MAX(criado_em) FROM public.sms_enviados WHERE usuario_id = $1",
        usuario_id,
    )
    candidatos = [t for t in (max_email, max_sms) if t is not None]
    return max(candidatos) if candidatos else None

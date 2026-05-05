from __future__ import annotations

import re
from typing import Any

import asyncpg

from app.config.postgres_identificadores import obter_identificadores_postgres


def _q_ident(ident: str) -> str:
    if re.match(r"^[a-z_][a-z0-9_]*$", ident):
        return ident
    return '"' + ident.replace('"', '""') + '"'


async def buscar_full_profile_por_cnpj_basico(
    pool: asyncpg.Pool,
    *,
    cnpj_basico: str,
) -> dict[str, Any] | None:
    p = obter_identificadores_postgres()
    qschema = _q_ident(p.schema)
    qtbl = _q_ident("company_profile")
    row = await pool.fetchrow(
        f"""
        SELECT full_profile
        FROM {qschema}.{qtbl}
        WHERE cnpj = $1
        LIMIT 1
        """,
        cnpj_basico,
    )
    if row is None:
        return None
    fp = row["full_profile"]
    if fp is None:
        return None
    if isinstance(fp, dict):
        return fp
    return None

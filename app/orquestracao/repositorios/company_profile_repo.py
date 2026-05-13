from __future__ import annotations
import re
from typing import Any
import asyncpg
from app.config.postgres_identificadores import obter_identificadores_postgres

def _q_ident(ident: str) -> str:
    if re.match(r"^[a-z_][a-z0-9_]*$", ident):
        return ident
    return '"' + ident.replace('"', '""') + '"'


def _uf_coluna_normalizada(row: Any) -> str | None:
    raw = row.get("uf")
    if raw is None:
        return None
    s = str(raw).strip()
    return s or None


async def buscar_full_profile_por_cnpj_basico(
    pool: asyncpg.Pool,
    *,
    cnpj_basico: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """``full_profile`` (JSON) e UF na coluna ``varchar`` ``uf``, quando existir na tabela."""
    p = obter_identificadores_postgres()
    qschema = _q_ident(p.schema)
    qtbl = _q_ident("company_profile")
    row = await pool.fetchrow(
        f"""
        SELECT full_profile, uf
        FROM {qschema}.{qtbl}
        WHERE cnpj = $1
        LIMIT 1
        """,
        cnpj_basico,
    )
    if row is None:
        return None, None
    uf_col = _uf_coluna_normalizada(row)
    fp = row["full_profile"]
    if fp is None:
        return None, uf_col
    if isinstance(fp, dict):
        return fp, uf_col
    return None, uf_col

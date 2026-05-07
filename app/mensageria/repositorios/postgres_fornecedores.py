"""Consultas mínimas a fornecedores na borda da mensageria."""

from __future__ import annotations

import uuid

import asyncpg

from app.config.postgres_identificadores import obter_identificadores_postgres


async def fornecedor_id_existe(pool: asyncpg.Pool, fornecedor_id: uuid.UUID) -> bool:
    p = obter_identificadores_postgres()
    t = p.qual("fornecedores")
    cf = p.col_usuario_fornecedor_id
    return await pool.fetchval(
        f"SELECT EXISTS (SELECT 1 FROM {t} WHERE {cf} = $1)",
        fornecedor_id,
    )


async def buscar_cnpj_basico_por_fornecedor_id(
    pool: asyncpg.Pool,
    fornecedor_id: uuid.UUID,
) -> str | None:
    p = obter_identificadores_postgres()
    t = p.qual("fornecedores")
    cf = p.col_usuario_fornecedor_id
    val = await pool.fetchval(
        f"""
        SELECT NULLIF(trim(COALESCE(uf.cnpj_basico::text, '')), '')
        FROM {t} AS uf
        WHERE uf.{cf} = $1
        """,
        fornecedor_id,
    )
    if val is None:
        return None
    return str(val).strip() or None


async def resolver_cnpj_basico_para_envio_mensagem(
    pool: asyncpg.Pool,
    *,
    cnpj_basico: str | None,
    fornecedor_id: uuid.UUID | None,
) -> str:
    """CNPJ básico do pedido ou, se ausente, o cadastrado em ``usuario_fornecedor``."""
    cnpj = (cnpj_basico or "").strip()
    if cnpj:
        return cnpj
    if fornecedor_id is not None:
        resolved = await buscar_cnpj_basico_por_fornecedor_id(pool, fornecedor_id)
        if resolved:
            return resolved
    raise ValueError(
        "informe cnpj_basico ou use fornecedor_id com CNPJ básico cadastrado para validar o envio."
    )


async def listar_fornecedores_diagnostico(
    pool: asyncpg.Pool,
    *,
    limite: int,
) -> list[dict[str, object]]:
    """SELECT somente leitura; nomes de tabela/coluna vêm de ``postgres_identificadores``."""
    p = obter_identificadores_postgres()
    t = p.qual("fornecedores")
    cf = p.col_usuario_fornecedor_id
    rows = await pool.fetch(
        f"SELECT * FROM {t} ORDER BY {cf} ASC LIMIT $1",
        limite,
    )
    return [dict(r) for r in rows]

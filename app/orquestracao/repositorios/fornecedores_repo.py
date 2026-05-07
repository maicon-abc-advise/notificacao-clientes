from __future__ import annotations

import asyncpg

from app.config.postgres_identificadores import obter_identificadores_postgres


async def buscar_usuario_fornecedor_por_cnpj_partes(
    pool: asyncpg.Pool,
    *,
    cnpj_basico: str,
    cnpj_ordem: str,
    cnpj_dv: str,
) -> asyncpg.Record:
    """Retorna usuário fornecedor por CNPJ; sem criar/alterar linha."""
    p = obter_identificadores_postgres()
    t = p.qual("fornecedores")
    ufid = p.col_usuario_fornecedor_id
    row = await pool.fetchrow(
        f"""
        SELECT
            uf.{ufid} AS fornecedor_id,
            uf.nome,
            uf.telefone,
            uf.cnpj,
            uf.cnpj_basico,
            uf.cnpj_ordem,
            uf.cnpj_dv,
            uf.n_creditos,
            au.email
        FROM {t} AS uf
        LEFT JOIN auth.users AS au ON au.id = uf.{ufid}
        WHERE uf.cnpj_basico = $1
          AND uf.cnpj_ordem = $2
          AND uf.cnpj_dv = $3
        LIMIT 1
        """,
        cnpj_basico,
        cnpj_ordem,
        cnpj_dv,
    )
    if row is None:
        raise LookupError("usuario_fornecedor não encontrado para o CNPJ informado")
    return row


async def listar_fornecedores_alerta_creditos(
    pool: asyncpg.Pool,
    *,
    limiar: int,
) -> list[asyncpg.Record]:
    """Usuários fornecedores com canal e n_creditos zerado/no limiar."""
    p = obter_identificadores_postgres()
    t = p.qual("fornecedores")
    ufid = p.col_usuario_fornecedor_id
    return await pool.fetch(
        f"""
        SELECT
            uf.{ufid} AS fornecedor_id,
            uf.nome,
            au.email,
            uf.telefone,
            uf.cnpj_basico,
            uf.cnpj_ordem,
            uf.cnpj_dv,
            uf.n_creditos AS creditos
        FROM {t} AS uf
        LEFT JOIN auth.users AS au ON au.id = uf.{ufid}
        WHERE (
              NULLIF(trim(au.email), '') IS NOT NULL
              OR NULLIF(trim(uf.telefone), '') IS NOT NULL
          )
          AND (
              uf.n_creditos = 0
              OR (uf.n_creditos > 0 AND uf.n_creditos <= $1)
          )
        ORDER BY uf.{ufid}
        """,
        limiar,
    )

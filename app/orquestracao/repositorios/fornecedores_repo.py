from __future__ import annotations

import uuid

import asyncpg

from app.config.postgres_identificadores import obter_identificadores_postgres


async def obter_ou_criar_e_incrementar_aparicao(
    pool: asyncpg.Pool,
    *,
    cnpj: str,
    nome: str | None,
    email: str | None,
    telefone: str | None,
) -> asyncpg.Record:
    """Garante linha em `fornecedores`, incrementa `aparicoes_busca` e preenche contato quando vier no payload."""
    p = obter_identificadores_postgres()
    t = p.qual("fornecedores")
    cf = p.col_fornecedor_id
    row = await pool.fetchrow(
        f"""
        INSERT INTO {t} (cnpj, nome, email, telefone, aparicoes_busca, creditos, ativo)
        VALUES ($1, $2, $3, $4, 1, 0, true)
        ON CONFLICT (cnpj) DO UPDATE SET
            nome = COALESCE(EXCLUDED.nome, {t}.nome),
            email = COALESCE(NULLIF(EXCLUDED.email, ''), {t}.email),
            telefone = COALESCE(NULLIF(EXCLUDED.telefone, ''), {t}.telefone),
            aparicoes_busca = {t}.aparicoes_busca + 1,
            updated_at = now()
        RETURNING
            {cf},
            cnpj,
            nome,
            email,
            telefone,
            ativo,
            aparicoes_busca
        """,
        cnpj,
        nome,
        email or None,
        telefone or None,
    )
    assert row is not None
    return row


async def listar_fornecedores_alerta_creditos(
    pool: asyncpg.Pool,
    *,
    limiar: int,
) -> list[asyncpg.Record]:
    """Fornecedores ativos com e-mail ou telefone, créditos zerados ou até o limiar (inclusive)."""
    p = obter_identificadores_postgres()
    t = p.qual("fornecedores")
    cf = p.col_fornecedor_id
    return await pool.fetch(
        f"""
        SELECT
            {cf},
            nome,
            email,
            telefone,
            creditos
        FROM {t}
        WHERE ativo = true
          AND (
              NULLIF(trim(email), '') IS NOT NULL
              OR NULLIF(trim(telefone), '') IS NOT NULL
          )
          AND (
              creditos = 0
              OR (creditos > 0 AND creditos <= $1)
          )
        ORDER BY {cf}
        """,
        limiar,
    )


async def atualizar_contato_apos_enriquecimento(
    pool: asyncpg.Pool,
    *,
    fornecedor_id: uuid.UUID,
    email: str | None,
    telefone: str | None,
) -> None:
    p = obter_identificadores_postgres()
    t = p.qual("fornecedores")
    cf = p.col_fornecedor_id
    await pool.execute(
        f"""
        UPDATE {t} SET
            email = COALESCE(NULLIF($2, ''), email),
            telefone = COALESCE(NULLIF($3, ''), telefone),
            updated_at = now()
        WHERE {cf} = $1
        """,
        fornecedor_id,
        email or "",
        telefone or "",
    )

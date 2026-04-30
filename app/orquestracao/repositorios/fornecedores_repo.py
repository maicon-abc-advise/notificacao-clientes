from __future__ import annotations

import uuid

import asyncpg


async def obter_ou_criar_e_incrementar_aparicao(
    pool: asyncpg.Pool,
    *,
    cnpj: str,
    nome: str | None,
    email: str | None,
    telefone: str | None,
) -> asyncpg.Record:
    """Garante linha em `fornecedores`, incrementa `aparicoes_busca` e preenche contato quando vier no payload."""
    row = await pool.fetchrow(
        """
        INSERT INTO public.fornecedores (cnpj, nome, email, telefone, aparicoes_busca, creditos)
        VALUES ($1, $2, $3, $4, 1, 0)
        ON CONFLICT (cnpj) DO UPDATE SET
            nome = COALESCE(EXCLUDED.nome, public.fornecedores.nome),
            email = COALESCE(NULLIF(EXCLUDED.email, ''), public.fornecedores.email),
            telefone = COALESCE(NULLIF(EXCLUDED.telefone, ''), public.fornecedores.telefone),
            aparicoes_busca = public.fornecedores.aparicoes_busca + 1,
            updated_at = now()
        RETURNING
            fornecedor_id,
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
    return await pool.fetch(
        """
        SELECT
            fornecedor_id,
            nome,
            email,
            telefone,
            creditos
        FROM public.fornecedores
        WHERE ativo = true
          AND (
              NULLIF(trim(email), '') IS NOT NULL
              OR NULLIF(trim(telefone), '') IS NOT NULL
          )
          AND (
              creditos = 0
              OR (creditos > 0 AND creditos <= $1)
          )
        ORDER BY fornecedor_id
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
    await pool.execute(
        """
        UPDATE public.fornecedores SET
            email = COALESCE(NULLIF($2, ''), email),
            telefone = COALESCE(NULLIF($3, ''), telefone),
            updated_at = now()
        WHERE fornecedor_id = $1
        """,
        fornecedor_id,
        email or "",
        telefone or "",
    )

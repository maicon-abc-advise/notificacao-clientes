"""Rota de diagnóstico: leitura de fornecedores (tabela física conforme POSTGRES_TABELA_SUFFIX)."""

from __future__ import annotations

from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, Query

from app.config.postgres_identificadores import obter_identificadores_postgres
from app.iam.dependencias import verificar_chamada_interna
from app.mensageria.repositorios.postgres_fornecedores import listar_fornecedores_diagnostico
from app.templates.conexao import obter_pool

router = APIRouter(
    prefix="/v1/mensagens",
    dependencies=[Depends(verificar_chamada_interna)],
)


async def _pool() -> asyncpg.Pool:
    return await obter_pool()


@router.get(
    "/diagnostico/fornecedores",
    summary="Diagnóstico: listar fornecedores (somente leitura)",
    description=(
        "Executa apenas ``SELECT`` na tabela de fornecedores resolvida pelo ambiente "
        "(ex.: ``fornecedores_teste`` quando ``POSTGRES_TABELA_SUFFIX=_teste``). "
        "Não altera nem apaga dados."
    ),
)
async def get_diagnostico_fornecedores(
    pool: Annotated[asyncpg.Pool, Depends(_pool)],
    limite: Annotated[int, Query(ge=1, le=50, description="Máximo de linhas")] = 10,
) -> dict[str, object]:
    p = obter_identificadores_postgres()
    tabela_fisica = f"{p.schema}.{p.nome_fisico_tabela('fornecedores')}"
    linhas = await listar_fornecedores_diagnostico(pool, limite=limite)
    return {
        "tabela": tabela_fisica,
        "postgres_schema": p.schema,
        "postgres_tabela_suffix": p.tabela_suffix or "",
        "coluna_fornecedor_id": p.col_fornecedor_id,
        "limite": limite,
        "total_retorno": len(linhas),
        "linhas": linhas,
    }

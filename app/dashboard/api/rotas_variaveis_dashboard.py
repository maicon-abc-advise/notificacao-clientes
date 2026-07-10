"""API dashboard — variáveis de sistema."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config.variaveis_sistema.modelo import (
    CorpoAtualizarVariavel,
    RespostaListagemVariaveis,
    VariavelSistemaItem,
)
from app.config.variaveis_sistema.servico import atualizar_variavel, listar_para_dashboard
from app.iam.rotas.dashboard_rotas import usuario_logado
from app.orquestracao.api.dependencias import PoolOrquestracao

router = APIRouter(
    prefix="/v1/interno/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(usuario_logado)],
)


@router.get("/variaveis", response_model=RespostaListagemVariaveis)
async def get_variaveis_sistema(pool: PoolOrquestracao) -> RespostaListagemVariaveis:
    return await listar_para_dashboard(pool)


@router.patch("/variaveis/{chave}", response_model=VariavelSistemaItem)
async def patch_variavel_sistema(
    chave: str,
    corpo: CorpoAtualizarVariavel,
    pool: PoolOrquestracao,
) -> VariavelSistemaItem:
    return await atualizar_variavel(pool, chave, corpo)

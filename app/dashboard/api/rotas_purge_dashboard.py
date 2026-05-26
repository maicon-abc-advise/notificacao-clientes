"""Purge temporário de incidente (preview + execução)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.dashboard.api.dto.mutacoes_dashboard import CorpoConfirmacaoSenha
from app.dashboard.servicos import purge_incidente_servico as purge
from app.iam.rotas.dashboard_rotas import usuario_logado
from app.orquestracao.api.dependencias import PoolOrquestracao, RedisOrquestracao

router = APIRouter(
    prefix="/v1/interno/dashboard/purge",
    tags=["dashboard-purge"],
    dependencies=[Depends(usuario_logado)],
)

SessaoDashboard = Annotated[dict[str, Any], Depends(usuario_logado)]


@router.get("/preview")
async def purge_preview(
    pool: PoolOrquestracao,
    redis: RedisOrquestracao,
) -> dict[str, Any]:
    return await purge.montar_preview(pool, redis)


@router.post("/executar")
async def purge_executar(
    pool: PoolOrquestracao,
    redis: RedisOrquestracao,
    sessao: SessaoDashboard,
    payload: CorpoConfirmacaoSenha,
) -> dict[str, Any]:
    return await purge.executar_purge(pool, redis, sessao=sessao, senha=payload.senha)

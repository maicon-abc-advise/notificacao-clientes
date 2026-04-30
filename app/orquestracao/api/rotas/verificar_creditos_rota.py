from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.config.config import Configuracao, obter_configuracao
from app.orquestracao.api.dependencias import PoolOrquestracao, RedisOrquestracao
from app.orquestracao.api.dto import RespostaVerificarCreditos
from app.orquestracao.servicos.verificar_creditos_servico import executar_verificar_creditos

router = APIRouter()


@router.post(
    "/verificar-creditos",
    response_model=RespostaVerificarCreditos,
    status_code=status.HTTP_200_OK,
    summary="Varre fornecedores no limiar de créditos e enfileira e-mail ou SMS (LIMIAR_CREDITOS_NO_FIM / coluna creditos)",
)
async def post_verificar_creditos(
    pool: PoolOrquestracao,
    redis: RedisOrquestracao,
    config: Annotated[Configuracao, Depends(obter_configuracao)],
) -> RespostaVerificarCreditos:
    return await executar_verificar_creditos(pool, redis, config)

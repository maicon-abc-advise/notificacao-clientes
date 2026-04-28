from __future__ import annotations

from fastapi import APIRouter, status

from app.orquestracao.api.dependencias import PoolOrquestracao, RedisOrquestracao
from app.orquestracao.api.dto import RespostaVerificarCreditos, VerificarCreditosCorpo
from app.orquestracao.servicos.verificar_creditos_servico import executar_verificar_creditos

router = APIRouter()


@router.post(
    "/verificar-creditos",
    response_model=RespostaVerificarCreditos,
    status_code=status.HTTP_200_OK,
    summary="Avalia créditos e enfileira e-mail de aviso quando aplicável",
)
async def post_verificar_creditos(
    corpo: VerificarCreditosCorpo,
    pool: PoolOrquestracao,
    redis: RedisOrquestracao,
) -> RespostaVerificarCreditos:
    return await executar_verificar_creditos(pool, redis, corpo)

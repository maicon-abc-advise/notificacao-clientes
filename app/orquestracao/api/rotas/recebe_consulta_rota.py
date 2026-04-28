from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.orquestracao.api.dependencias import PoolOrquestracao, PortaEnriquecimento, RedisOrquestracao
from app.orquestracao.api.dto import RecebeConsultaCorpo, RespostaRecebeConsulta
from app.orquestracao.excecoes import ConsultaJaNotificadaError, ConsultaNaoEncontradaError
from app.orquestracao.servicos.receber_consulta_servico import executar_receber_consulta

router = APIRouter()


@router.post(
    "/recebe-consulta",
    response_model=RespostaRecebeConsulta,
    status_code=status.HTTP_200_OK,
    summary="Orquestra notificação a partir de uma consulta existente",
)
async def post_recebe_consulta(
    corpo: RecebeConsultaCorpo,
    pool: PoolOrquestracao,
    redis: RedisOrquestracao,
    porta: PortaEnriquecimento,
) -> RespostaRecebeConsulta:
    try:
        return await executar_receber_consulta(pool, redis, porta, corpo)
    except ConsultaNaoEncontradaError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except ConsultaJaNotificadaError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e

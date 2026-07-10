from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from redis.asyncio import Redis

from app.config.dependencias import obter_porta_envio_mensagem
from app.config.dependencias_templates import PortaTemplatesDep
from app.mensageria.servicos.porta import PortaEnvioMensagem
from app.orquestracao.api.dependencias import PoolOrquestracao
from app.orquestracao.api.dto.comprador_busca_dto import (
    PedidoEnviarCompradorBusca,
    PedidoSmsCompradorBusca,
    RespostaEnviarCompradorBusca,
    RespostaSmsCompradorBusca,
)
from app.orquestracao.servicos.enviar_comprador_busca import executar_envio_comprador_busca
from app.orquestracao.servicos.enviar_sms_comprador_busca import executar_envio_sms_comprador_busca
from app.reenvio.redis_app import obter_cliente_redis

router = APIRouter()


async def _redis() -> Redis:
    return await obter_cliente_redis()


@router.post(
    "/comprador-busca/sms",
    response_model=RespostaSmsCompradorBusca,
    status_code=status.HTTP_200_OK,
    summary="Envia SMS com resultado da busca para comprador (WhatsApp)",
)
async def post_sms_comprador_busca(
    corpo: PedidoSmsCompradorBusca,
    pool: PoolOrquestracao,
    redis: Annotated[Redis, Depends(_redis)],
    porta: Annotated[PortaEnvioMensagem, Depends(obter_porta_envio_mensagem)],
    templates: PortaTemplatesDep,
) -> RespostaSmsCompradorBusca:
    return await executar_envio_sms_comprador_busca(
        pool,
        redis,
        corpo,
        porta=porta,
        templates=templates,
    )


@router.post(
    "/comprador-busca/enviar",
    response_model=RespostaEnviarCompradorBusca,
    status_code=status.HTTP_200_OK,
    summary="Notifica comprador após busca (multicanal; hoje apenas SMS)",
)
async def post_enviar_comprador_busca(
    corpo: PedidoEnviarCompradorBusca,
    pool: PoolOrquestracao,
    redis: Annotated[Redis, Depends(_redis)],
    porta: Annotated[PortaEnvioMensagem, Depends(obter_porta_envio_mensagem)],
    templates: PortaTemplatesDep,
) -> RespostaEnviarCompradorBusca:
    return await executar_envio_comprador_busca(
        pool,
        redis,
        corpo,
        porta=porta,
        templates=templates,
    )

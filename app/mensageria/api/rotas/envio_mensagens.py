from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis

from app.config.dependencias import obter_porta_envio_mensagem
from app.config.dependencias_templates import PortaTemplatesDep
from app.iam.dependencias import verificar_chamada_interna
from app.mensageria.api.dto.modelos import (
    PedidoEnvioEmail,
    PedidoEnvioSms,
    ResultadoEnvioMensagem,
)
from app.mensageria.excecoes.erro import ErroEnvioZenvia
from app.mensageria.servicos.executar_envio_mensagem import executar_envio_email, executar_envio_sms
from app.mensageria.servicos.porta import PortaEnvioMensagem
from app.reenvio.redis_app import obter_cliente_redis
from app.templates.conexao import obter_pool

router = APIRouter(
    prefix="/v1/mensagens",
    dependencies=[Depends(verificar_chamada_interna)],
)


async def _pool_mensagens() -> asyncpg.Pool:
    return await obter_pool()


async def _redis_mensagens() -> Redis:
    return await obter_cliente_redis()


@router.post("/email", response_model=ResultadoEnvioMensagem, status_code=status.HTTP_200_OK)
async def post_enviar_email(
    pedido: PedidoEnvioEmail,
    porta: Annotated[PortaEnvioMensagem, Depends(obter_porta_envio_mensagem)],
    templates: PortaTemplatesDep,
    pool: Annotated[asyncpg.Pool, Depends(_pool_mensagens)],
) -> ResultadoEnvioMensagem:
    try:
        return await executar_envio_email(pool, pedido, porta=porta, templates=templates)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except ErroEnvioZenvia as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e)[:2000],
        ) from e


@router.post("/sms", response_model=ResultadoEnvioMensagem, status_code=status.HTTP_200_OK)
async def post_enviar_sms(
    pedido: PedidoEnvioSms,
    porta: Annotated[PortaEnvioMensagem, Depends(obter_porta_envio_mensagem)],
    templates: PortaTemplatesDep,
    pool: Annotated[asyncpg.Pool, Depends(_pool_mensagens)],
    redis: Annotated[Redis, Depends(_redis_mensagens)],
) -> ResultadoEnvioMensagem:
    try:
        return await executar_envio_sms(pool, redis, pedido, porta=porta, templates=templates)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except ErroEnvioZenvia as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e)[:2000],
        ) from e

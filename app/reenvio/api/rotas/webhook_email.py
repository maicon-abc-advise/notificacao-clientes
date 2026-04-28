"""Webhook manual/teste para **status de e-mail** (MESSAGE_STATUS, channel email).

Validação estrita do JSON + ``X-Webhook-Secret`` quando ``ZENVIA_WEBHOOK_SECRET``
está definido. Atualiza Redis (``emails-esperando-confirmacao``) e pode enfileirar na fila **sms-pendente** no Redis.
"""

from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, status
from redis.asyncio import Redis
from app.config.config import Configuracao, obter_configuracao
from app.reenvio.api.dependencias_webhook import verificar_segredo_webhook_zenvia
from app.reenvio.api.dto.webhook_zenvia import WebhookMessageStatusZenvia
from app.reenvio.redis_app import obter_cliente_redis
from app.reenvio.servicos.processar_status_email import processar_webhook_status_email
from app.templates.conexao import obter_pool

router = APIRouter(
    prefix="/v1/webhooks/zenvia",
    tags=["webhooks-zenvia-email"],
    dependencies=[Depends(verificar_segredo_webhook_zenvia)],
)

async def _pool() -> asyncpg.Pool:
    return await obter_pool()

async def _redis() -> Redis:
    return await obter_cliente_redis()

@router.post(
    "/email",
    status_code=status.HTTP_200_OK,
    summary="Webhook Zenvia — status de e-mail",
)
async def post_webhook_email_status(
    corpo: WebhookMessageStatusZenvia,
    pool: Annotated[asyncpg.Pool, Depends(_pool)],
    redis: Annotated[Redis, Depends(_redis)],
    config: Annotated[Configuracao, Depends(obter_configuracao)],
) -> dict:
    if corpo.channel != "email":
        return {"erro": "esta rota aceita apenas channel=email", "recebido": corpo.channel}
    resultado = await processar_webhook_status_email(pool, redis, config, corpo)
    return resultado

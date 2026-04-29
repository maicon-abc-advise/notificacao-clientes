from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, status
from redis.asyncio import Redis

from app.config.config import Configuracao, obter_configuracao
from app.iam.dependencias import verificar_chamada_interna
from app.reenvio.redis_app import obter_cliente_redis
from app.reenvio.repositorios.redis_sms_pendente import RepositorioSmsPendenteRedis
from app.reenvio.servicos.sweep_emails_pendentes import executar_sweep_emails_pendentes
from app.templates.conexao import obter_pool

router = APIRouter(
    prefix="/v1/interno",
    tags=["interno-reenvio"],
    dependencies=[Depends(verificar_chamada_interna)],
)


async def _redis() -> Redis:
    return await obter_cliente_redis()


async def _pool() -> asyncpg.Pool:
    return await obter_pool()


async def _executar_sweep_emails_esperando_confirmacao(
    pool: asyncpg.Pool,
    redis: Redis,
    config: Configuracao,
) -> dict:
    return await executar_sweep_emails_pendentes(pool, redis, config)


@router.post(
    "/sweep-emails-esperando-confirmacao",
    status_code=status.HTTP_200_OK,
    summary="Coloca SMS na fila sms-pendente (e-mails ainda em emails-esperando-confirmacao no Redis)",
)
async def post_sweep_emails_esperando_confirmacao(
    pool: Annotated[asyncpg.Pool, Depends(_pool)],
    redis: Annotated[Redis, Depends(_redis)],
    config: Annotated[Configuracao, Depends(obter_configuracao)],
) -> dict:
    return await _executar_sweep_emails_esperando_confirmacao(pool, redis, config)


@router.get(
    "/sms-pendentes",
    status_code=status.HTTP_200_OK,
    summary="Lista SMS ainda na fila Redis (para o n8n consumir)",
)
async def get_sms_pendentes(
    redis: Annotated[Redis, Depends(_redis)],
    limite: int = 200,
) -> dict:
    repo = RepositorioSmsPendenteRedis()
    itens = await repo.listar_pendentes(redis, limite=max(1, min(limite, 500)))
    return {"total": len(itens), "itens": itens}

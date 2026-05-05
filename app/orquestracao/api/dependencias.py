from __future__ import annotations
from typing import Annotated
import asyncpg
from fastapi import Depends
from redis.asyncio import Redis
from app.config.config import Configuracao, obter_configuracao
from app.orquestracao.externo.company_profile import AdaptadorCompanyProfileMock, AdaptadorCompanyProfilePostgres
from app.orquestracao.servicos.auxiliares.porta_enriquecimento_contato import PortaEnriquecimentoContato
from app.reenvio.redis_app import obter_cliente_redis
from app.templates.conexao import obter_pool

async def _pool() -> asyncpg.Pool:
    return await obter_pool()

async def _redis() -> Redis:
    return await obter_cliente_redis()

async def obter_porta_enriquecimento_contato(
    config: Annotated[Configuracao, Depends(obter_configuracao)],
    pool: Annotated[asyncpg.Pool, Depends(_pool)],
) -> PortaEnriquecimentoContato:
    if config.mock_company_profile_enriquecimento:
        return AdaptadorCompanyProfileMock()
    return AdaptadorCompanyProfilePostgres(pool)

PoolOrquestracao = Annotated[asyncpg.Pool, Depends(_pool)]
RedisOrquestracao = Annotated[Redis, Depends(_redis)]
PortaEnriquecimento = Annotated[PortaEnriquecimentoContato, Depends(obter_porta_enriquecimento_contato)]

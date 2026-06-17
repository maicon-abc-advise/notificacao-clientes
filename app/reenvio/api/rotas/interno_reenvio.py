from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from redis.asyncio import Redis

from app.config.config import Configuracao, obter_configuracao
from app.iam.dependencias import verificar_chamada_interna
from app.reenvio.redis_app import obter_cliente_redis
from app.reenvio.repositorios.redis_sms_pendente import RepositorioSmsPendenteRedis
from app.reenvio.servicos.limpar_pendentes_ja_enviados import (
    executar_limpar_emails_pendentes_ja_enviados,
)
from app.reenvio.servicos.sweep_emails_pendentes import executar_sweep_emails_pendentes
from app.reenvio.servicos.migrar_contatos_sms_telefone_engajamento import (
    executar_migrar_contatos_sms_para_telefone_engajamento,
)
from app.reenvio.servicos.sweep_sms_esperando_confirmacao import (
    executar_sweep_sms_esperando_confirmacao,
)
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
    "/limpar-emails-pendentes-ja-enviados",
    status_code=status.HTTP_200_OK,
    summary="Remove da fila Redis e-mails que já constam em emails_enviados (fluxo travou após envio)",
)
async def post_limpar_emails_pendentes_ja_enviados(
    pool: Annotated[asyncpg.Pool, Depends(_pool)],
    redis: Annotated[Redis, Depends(_redis)],
    limite: Annotated[int, Query(ge=1, le=5000)] = 500,
) -> dict:
    return await executar_limpar_emails_pendentes_ja_enviados(pool, redis, limite=limite)


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


@router.post(
    "/sweep-sms-esperando-confirmacao",
    status_code=status.HTTP_200_OK,
    summary="Reenfileira SMS (sms-pendente) a partir de sms-esperando-confirmacao após o prazo do sweep",
)
async def post_sweep_sms_esperando_confirmacao(
    pool: Annotated[asyncpg.Pool, Depends(_pool)],
    redis: Annotated[Redis, Depends(_redis)],
    config: Annotated[Configuracao, Depends(obter_configuracao)],
) -> dict:
    return await executar_sweep_sms_esperando_confirmacao(pool, redis, config)


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


@router.post(
    "/migrar-telefone-engajamento",
    status_code=status.HTTP_200_OK,
    summary="Migra contatos_sms (JSON) de engajamento_fornecedores para telefone_engajamento (canal sms)",
)
async def post_migrar_telefone_engajamento(
    pool: Annotated[asyncpg.Pool, Depends(_pool)],
    cnpj_basico: Annotated[str | None, Query(min_length=8, max_length=8)] = None,
    limite: Annotated[int | None, Query(ge=1, le=50_000)] = None,
    dry_run: Annotated[bool, Query()] = False,
) -> dict:
    try:
        return await executar_migrar_contatos_sms_para_telefone_engajamento(
            pool,
            cnpj_basico=cnpj_basico,
            limite=limite,
            dry_run=dry_run,
        )
    except asyncpg.PostgresError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro Postgres na migração: {exc}",
        ) from exc

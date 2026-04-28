from contextlib import asynccontextmanager
import logging

import asyncpg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config.config import obter_configuracao
from app.iam.rotas import ping_autenticado
from app.mensageria.api.rotas import envio_mensagens, saude
from app.reenvio.api.rotas import (
    interno_reenvio_router,
    teste_pipeline_router,
    webhook_email_router,
    webhook_sms_router,
)
from app.orquestracao.api import orquestracao_router
from app.reenvio.redis_app import fechar_cliente_redis, obter_cliente_redis
from app.templates.conexao import fechar_pool


def _configurar_logging() -> None:
    """Sem isto, loggers da app ficam no nível WARNING do root e INFO não aparece no terminal."""
    cfg = obter_configuracao()
    nivel = getattr(logging, cfg.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=nivel,
        format="%(levelname)s [%(name)s] %(message)s",
        force=True,
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _configurar_logging()
    await obter_cliente_redis()
    yield
    await fechar_pool()
    await fechar_cliente_redis()


app = FastAPI(
    title="API do sistema de notificações da ABC Advise",
    description="Infraestrutura inicial",
    lifespan=lifespan,
)


@app.exception_handler(asyncpg.exceptions.UndefinedTableError)
async def _sem_tabela_postgres(_request: Request, _exc: asyncpg.exceptions.UndefinedTableError) -> JSONResponse:
    """Evita 500 genérico quando o schema (ex. reenvio) ainda não foi aplicado na base."""
    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                "Postgres sem tabela necessária. Na pasta do projeto, com DATABASE_URL correto no ambiente, "
                "execute: python -m app.reenvio.aplicar_schema"
            ),
        },
    )


app.include_router(saude.router, tags=["saúde"])
app.include_router(ping_autenticado.router, tags=["autenticação"])
app.include_router(envio_mensagens.router, tags=["envio"])
app.include_router(webhook_email_router)
app.include_router(webhook_sms_router)
app.include_router(interno_reenvio_router)
app.include_router(teste_pipeline_router)
app.include_router(orquestracao_router)

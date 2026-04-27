from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.iam.rotas import ping_autenticado
from app.mensageria.api.rotas import envio_mensagens, saude
from app.reenvio.api.rotas import (
    interno_reenvio_router,
    teste_pipeline_router,
    webhook_email_router,
    webhook_sms_router,
)
from app.reenvio.redis_app import fechar_cliente_redis, obter_cliente_redis
from app.templates.conexao import fechar_pool


@asynccontextmanager
async def lifespan(_app: FastAPI):
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

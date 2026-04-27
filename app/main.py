from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.iam.rotas import ping_autenticado
from app.mensageria.api.rotas import envio_mensagens, saude
from app.templates.conexao import fechar_pool


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    await fechar_pool()


app = FastAPI(
    title="API do sistema de notificações da ABC Advise",
    description="Infraestrutura inicial",
    lifespan=lifespan,
)

app.include_router(saude.router, tags=["saúde"])
app.include_router(ping_autenticado.router, tags=["autenticação"])
app.include_router(envio_mensagens.router, tags=["envio"])

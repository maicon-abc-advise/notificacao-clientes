from fastapi import FastAPI

from app.rotas import ping_autenticado, saude

app = FastAPI(
    title="API do sistema de notificações da ABC Advise",
    description="Infraestrutura inicial",
)

app.include_router(saude.router, tags=["saúde"])
app.include_router(ping_autenticado.router, tags=["autenticação"])

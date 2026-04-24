"""Ponto de entrada da aplicação FastAPI."""

from fastapi import FastAPI

from app.rotas import eventos_zenvia, notificacoes, saude

app = FastAPI(
    title="API do sistema de e-mail",
    description="Serviço de notificações (infraestrutura inicial).",
)

app.include_router(saude.router, tags=["saúde"])
app.include_router(notificacoes.router, prefix="/v1", tags=["notificações"])
app.include_router(eventos_zenvia.router, prefix="/v1", tags=["webhooks"])

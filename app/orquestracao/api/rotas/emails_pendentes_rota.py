from __future__ import annotations
from fastapi import APIRouter, status
from app.orquestracao.api.dependencias import RedisOrquestracao
from app.orquestracao.repositorios.redis_emails_pendentes_repo import RepositorioEmailsPendenteRedis
router = APIRouter()

@router.get(
    "/emails-pendentes",
    status_code=status.HTTP_200_OK,
    summary="Lista e-mails na fila Redis pré-envio (emails-pendentes)",
)
async def get_emails_pendentes(
    redis: RedisOrquestracao,
    limite: int = 200,
) -> dict:
    repo = RepositorioEmailsPendenteRedis()
    itens = await repo.listar_pendentes(redis, limite=max(1, min(limite, 500)))
    return {"total": len(itens), "itens": itens}

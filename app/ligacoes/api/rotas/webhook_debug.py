import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, status
from redis.asyncio import Redis

from app.ligacoes.repositorios.redis_webhook_debug import gravar_evento_webhook
from app.reenvio.redis_app import obter_cliente_redis

_log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/webhooks/vapi",
    tags=["ligações — webhook debug"],
)


async def _redis() -> Redis:
    return await obter_cliente_redis()


@router.post("/debug", status_code=status.HTTP_200_OK)
async def post_webhook_vapi_debug(
    request: Request,
    redis: Annotated[Redis, Depends(_redis)],
) -> dict[str, Any]:
    bruto = await request.body()
    payload: Any
    if not bruto:
        payload = {}
    else:
        try:
            payload = json.loads(bruto)
        except json.JSONDecodeError:
            payload = {"_raw": bruto.decode("utf-8", errors="replace")}

    evento = await gravar_evento_webhook(redis, payload)
    _log.info(
        "Webhook Vapi debug id=%s tipo=%s status=%s",
        evento.get("id"),
        evento.get("tipo"),
        evento.get("status"),
    )
    return {"ok": True, "evento_id": evento.get("id")}

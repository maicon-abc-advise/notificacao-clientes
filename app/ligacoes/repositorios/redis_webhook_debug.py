from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from redis.asyncio import Redis

KEY_EVENTOS = "vapi:webhook-debug:eventos"
MAX_EVENTOS = 200


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def extrair_rotulos_payload(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    """Tenta inferir tipo/status sem validar o schema do Vapi."""
    tipo: str | None = None
    status: str | None = None

    message = payload.get("message")
    if isinstance(message, dict):
        tipo = message.get("type") or message.get("status")
        status = message.get("status") or message.get("endedReason")

    if tipo is None:
        bruto = payload.get("type")
        if isinstance(bruto, str):
            tipo = bruto

    if status is None:
        bruto = payload.get("status")
        if isinstance(bruto, str):
            status = bruto

    call = payload.get("call")
    if isinstance(call, dict):
        if status is None and call.get("status"):
            status = str(call.get("status"))
        if tipo is None and call.get("type"):
            tipo = str(call.get("type"))

    return (
        str(tipo) if tipo is not None else None,
        str(status) if status is not None else None,
    )


async def gravar_evento_webhook(redis: Redis, payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        corpo = payload
    elif payload is None:
        corpo = {}
    else:
        corpo = {"valor": payload}

    tipo, status = extrair_rotulos_payload(corpo)
    evento = {
        "id": str(uuid.uuid4()),
        "recebido_em": _agora_iso(),
        "tipo": tipo,
        "status": status,
        "payload": corpo,
    }
    await redis.lpush(KEY_EVENTOS, json.dumps(evento, ensure_ascii=False))
    await redis.ltrim(KEY_EVENTOS, 0, MAX_EVENTOS - 1)
    return evento


async def listar_eventos_webhook(redis: Redis, *, limite: int = 100) -> list[dict[str, Any]]:
    limite = max(1, min(limite, MAX_EVENTOS))
    brutos = await redis.lrange(KEY_EVENTOS, 0, limite - 1)
    eventos: list[dict[str, Any]] = []
    for bruto in brutos:
        try:
            if isinstance(bruto, bytes):
                bruto = bruto.decode("utf-8")
            eventos.append(json.loads(bruto))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
    return eventos

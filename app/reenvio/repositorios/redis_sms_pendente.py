"""Fila Redis: SMS ainda **não** enviados (só o n8n / consumidor apaga após disparo).

Chaves:
- ``sms:pendente:{external_id}`` — hash com payload para ``POST /v1/mensagens/sms``.
- ``sms:pendente:por_tempo`` — sorted set (score = epoch) para listar por ordem.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from redis.asyncio import Redis

_log = logging.getLogger(__name__)

KEY_INDEX = "sms:pendente:por_tempo"

def chave_hash(external_id: str) -> str:
    return f"sms:pendente:{external_id}"

class RepositorioSmsPendenteRedis:
    async def criar(
        self,
        redis: Redis,
        *,
        external_id: str,
        telefone: str,
        tipo_template: str,
        contexto: dict[str, str],
        remetente: str | None,
        origem: str,
        usuario_id: str | None = None,
    ) -> bool:
    
        key = chave_hash(external_id)
        if await redis.exists(key):
            return False
        agora = int(time.time())
        mapping: dict[str, str] = {
            "external_id": external_id,
            "telefone": telefone,
            "tipo_template": tipo_template,
            "contexto_json": json.dumps(contexto, ensure_ascii=False),
            "remetente": remetente or "",
            "origem": origem,
            "usuario_id": usuario_id or "",
            "criado_em": str(agora),
        }
        pipe = redis.pipeline(transaction=True)
        pipe.hset(key, mapping=mapping)
        pipe.zadd(KEY_INDEX, {external_id: float(agora)})
        await pipe.execute()
        _log.info("SMS pendente Redis: external_id=%s origem=%s", external_id, origem)
        return True

    async def remover(self, redis: Redis, external_id: str) -> None:
        pipe = redis.pipeline(transaction=True)
        pipe.delete(chave_hash(external_id))
        pipe.zrem(KEY_INDEX, external_id)
        await pipe.execute()

    async def listar_pendentes(self, redis: Redis, *, limite: int = 200) -> list[dict[str, Any]]:
        """Lista hashes de SMS pendentes (por ordem de entrada no índice)."""
        ids = await redis.zrange(KEY_INDEX, 0, limite - 1)
        saida: list[dict[str, Any]] = []
        for ext in ids:
            raw = await redis.hgetall(chave_hash(ext))
            if not raw:
                await redis.zrem(KEY_INDEX, ext)
                continue
            ctx = json.loads(raw.get("contexto_json") or "{}")
            saida.append(
                {
                    "external_id": raw.get("external_id", ext),
                    "telefone": raw.get("telefone", ""),
                    "tipo_template": raw.get("tipo_template", ""),
                    "contexto": ctx if isinstance(ctx, dict) else {},
                    "remetente": raw.get("remetente") or None,
                    "origem": raw.get("origem", ""),
                    "usuario_id": raw.get("usuario_id") or None,
                    "criado_em": raw.get("criado_em"),
                },
            )
        return saida

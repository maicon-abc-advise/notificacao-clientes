from __future__ import annotations
import json
import logging
import time
from typing import Any
from redis.asyncio import Redis
_log = logging.getLogger(__name__)
KEY_SWEEP = "email:pendente:sweep"

def chave_hash(message_id: str) -> str:
    return f"email:pendente:{message_id}"

def chave_external(external_id: str) -> str:
    return f"email:pendente:ext:{external_id}"

class RepositorioEmailPendenteRedis:
    async def criar_apos_envio(
        self,
        redis: Redis,
        *,
        message_id: str,
        external_id: str,
        email_destinatario: str,
        tipo_template: str,
        contexto: dict[str, str],
        remetente: str | None,
        telefone_sms_fallback: str | None,
        sweep_score_ts: int,
        usuario_id: str | None = None,
    ) -> None:
        agora = str(int(time.time()))
        mapping: dict[str, str] = {
            "external_id": external_id,
            "email_destinatario": email_destinatario,
            "message_id_zenvia": message_id,
            "tipo_template": tipo_template,
            "contexto_json": json.dumps(contexto, ensure_ascii=False),
            "remetente": remetente or "",
            "telefone_sms_fallback": telefone_sms_fallback or "",
            "usuario_id": usuario_id or "",
            "status_atual": "AGUARDANDO_ABERTURA",
            "criado_em": agora,
            "atualizado_em": agora,
        }
        pipe = redis.pipeline(transaction=True)
        pipe.hset(chave_hash(message_id), mapping=mapping)
        pipe.set(chave_external(external_id), message_id)
        pipe.zadd(KEY_SWEEP, {message_id: float(sweep_score_ts)})
        await pipe.execute()
        _log.info(
            "E-mail enfileirado em Redis (pendente confirmação): message_id=%s external_id=%s",
            message_id,
            external_id,
        )

    async def obter(self, redis: Redis, message_id: str) -> dict[str, str] | None:
        raw = await redis.hgetall(chave_hash(message_id))
        return raw if raw else None

    async def atualizar_campos(self, redis: Redis, message_id: str, campos: dict[str, str]) -> None:
        campos["atualizado_em"] = str(int(time.time()))
        await redis.hset(chave_hash(message_id), mapping=campos)

    async def remover(self, redis: Redis, message_id: str) -> None:
        data = await redis.hgetall(chave_hash(message_id))
        ext = data.get("external_id") if data else None
        pipe = redis.pipeline(transaction=True)
        pipe.delete(chave_hash(message_id))
        pipe.zrem(KEY_SWEEP, message_id)
        if ext:
            pipe.delete(chave_external(ext))
        await pipe.execute()
        _log.info("E-mail removido da fila Redis: message_id=%s", message_id)

    async def reagendar_sweep(self, redis: Redis, message_id: str, novo_score_ts: int) -> None:
        await redis.zadd(KEY_SWEEP, {message_id: float(novo_score_ts)})

    async def listar_sweep_elegiveis(self, redis: Redis, *, ate_ts: int) -> list[str]:
        return list(
            await redis.zrangebyscore(KEY_SWEEP, "-inf", float(ate_ts)),
        )

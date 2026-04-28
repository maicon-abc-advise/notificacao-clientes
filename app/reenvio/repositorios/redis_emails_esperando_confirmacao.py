"""Redis: e-mails já enviados ao provedor, aguardando eventos (webhook) e sweep.

Chaves (namespace ``emails-esperando-confirmacao``):
- ``emails-esperando-confirmacao:{message_id}`` — hash com metadados do envio.
- ``emails-esperando-confirmacao:ext:{external_id}`` — message_id para lookup reverso.
- ``emails-esperando-confirmacao:sweep`` — sorted set (score = epoch elegível ao sweep).
"""
from __future__ import annotations
import json
import logging
import time
import uuid
from typing import Any

from redis.asyncio import Redis

from app.reenvio.repositorios.redis_consulta_notificacao import (
    fase_esperando_email,
    liberar_trava_se_fase,
    promover_para_esperando_email,
)

_log = logging.getLogger(__name__)

KEY_SWEEP = "emails-esperando-confirmacao:sweep"


def chave_hash(message_id: str) -> str:
    return f"emails-esperando-confirmacao:{message_id}"


def chave_external(external_id: str) -> str:
    return f"emails-esperando-confirmacao:ext:{external_id}"


class RepositorioEmailsEsperandoConfirmacaoRedis:
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
        consulta_id: uuid.UUID | None = None,
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
            "consulta_id": str(consulta_id) if consulta_id is not None else "",
            "status_atual": "AGUARDANDO_ABERTURA",
            "criado_em": agora,
            "atualizado_em": agora,
        }
        pipe = redis.pipeline(transaction=True)
        pipe.hset(chave_hash(message_id), mapping=mapping)
        pipe.set(chave_external(external_id), message_id)
        pipe.zadd(KEY_SWEEP, {message_id: float(sweep_score_ts)})
        await pipe.execute()
        await promover_para_esperando_email(redis, consulta_id, message_id)
        _log.info(
            "E-mail registado em Redis (esperando confirmação): message_id=%s external_id=%s",
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
        cid_raw = (data.get("consulta_id") or "").strip() if data else ""
        consulta_uuid: uuid.UUID | None = None
        if cid_raw:
            try:
                consulta_uuid = uuid.UUID(cid_raw)
            except ValueError:
                consulta_uuid = None
        pipe = redis.pipeline(transaction=True)
        pipe.delete(chave_hash(message_id))
        pipe.zrem(KEY_SWEEP, message_id)
        if ext:
            pipe.delete(chave_external(ext))
        await pipe.execute()
        await liberar_trava_se_fase(redis, consulta_uuid, fase_esperando_email(message_id))
        _log.info("E-mail removido do Redis (esperando confirmação): message_id=%s", message_id)

    async def reagendar_sweep(self, redis: Redis, message_id: str, novo_score_ts: int) -> None:
        await redis.zadd(KEY_SWEEP, {message_id: float(novo_score_ts)})

    async def listar_sweep_elegiveis(self, redis: Redis, *, ate_ts: int) -> list[str]:
        return list(
            await redis.zrangebyscore(KEY_SWEEP, "-inf", float(ate_ts)),
        )

from __future__ import annotations
import json
import logging
import time
import uuid
from typing import Any

from redis.asyncio import Redis

from app.orquestracao.excecoes import ConsultaJaNotificadaError
from app.reenvio.repositorios.redis_consulta_notificacao import (
    fase_pendente_email,
    liberar_trava_forcado,
    liberar_trava_se_fase,
    tentar_travar_pendente_email,
)

_log = logging.getLogger(__name__)

KEY_INDEX = "emails-pendentes:por_tempo"


def chave_hash(external_id: str) -> str:
    return f"emails-pendentes:{external_id}"


class RepositorioEmailsPendenteRedis:
    async def criar(
        self,
        redis: Redis,
        *,
        external_id: str,
        destinatario: str,
        tipo_template: str,
        contexto: dict[str, str],
        remetente: str | None,
        id_externo: str | None,
        telefone_sms_fallback: str | None,
        usuario_id: str | None,
        origem: str,
        consulta_id: uuid.UUID | None = None,
    ) -> bool:
        key = chave_hash(external_id)
        reservou_trava = False
        if consulta_id is not None:
            if not await tentar_travar_pendente_email(redis, consulta_id, external_id):
                raise ConsultaJaNotificadaError(str(consulta_id))
            reservou_trava = True
        try:
            if await redis.exists(key):
                if reservou_trava:
                    await liberar_trava_forcado(redis, consulta_id)
                return False
            agora = int(time.time())
            mapping: dict[str, str] = {
                "external_id": external_id,
                "destinatario": destinatario,
                "tipo_template": tipo_template,
                "contexto_json": json.dumps(contexto, ensure_ascii=False),
                "remetente": remetente or "",
                "id_externo_pedido": id_externo or "",
                "telefone_sms_fallback": telefone_sms_fallback or "",
                "usuario_id": usuario_id or "",
                "origem": origem,
                "consulta_id": str(consulta_id) if consulta_id is not None else "",
                "criado_em": str(agora),
            }
            pipe = redis.pipeline(transaction=True)
            pipe.hset(key, mapping=mapping)
            pipe.zadd(KEY_INDEX, {external_id: float(agora)})
            await pipe.execute()
        except Exception:
            if reservou_trava:
                await liberar_trava_forcado(redis, consulta_id)
            raise
        _log.info("E-mail na fila Redis (emails-pendentes): external_id=%s origem=%s", external_id, origem)
        return True

    async def remover(self, redis: Redis, external_id: str) -> None:
        key = chave_hash(external_id)
        raw = await redis.hgetall(key)
        cid_raw = (raw.get("consulta_id") or "").strip() if raw else ""
        consulta_uuid: uuid.UUID | None = None
        if cid_raw:
            try:
                consulta_uuid = uuid.UUID(cid_raw)
            except ValueError:
                consulta_uuid = None
        pipe = redis.pipeline(transaction=True)
        pipe.delete(key)
        pipe.zrem(KEY_INDEX, external_id)
        await pipe.execute()
        await liberar_trava_se_fase(redis, consulta_uuid, fase_pendente_email(external_id))

    async def listar_pendentes(self, redis: Redis, *, limite: int = 200) -> list[dict[str, Any]]:
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
                    "destinatario": raw.get("destinatario", ""),
                    "tipo_template": raw.get("tipo_template", ""),
                    "contexto": ctx if isinstance(ctx, dict) else {},
                    "remetente": raw.get("remetente") or None,
                    "id_externo": raw.get("id_externo_pedido") or None,
                    "telefone_sms_fallback": raw.get("telefone_sms_fallback") or None,
                    "usuario_id": raw.get("usuario_id") or None,
                    "origem": raw.get("origem", ""),
                    "consulta_id": raw.get("consulta_id") or None,
                    "criado_em": raw.get("criado_em"),
                },
            )
        return saida

"""Fila Redis: SMS ainda **não** enviados (o consumidor apaga após disparo).

Chaves (namespace ``sms-pendente``):
- ``sms-pendente:{id_externo}`` — hash com payload para ``POST /v1/mensagens/sms``.
- ``sms-pendente:por_tempo`` — sorted set (score = epoch) para listar por ordem.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from redis.asyncio import Redis

from app.orquestracao.excecoes import ConsultaJaNotificadaError
from app.reenvio.repositorios.redis_consulta_notificacao import (
    fase_pendente_sms,
    liberar_trava_forcado,
    liberar_trava_se_fase,
    redefinir_para_pendente_sms_pos_bounce,
    tentar_travar_pendente_sms,
)

_log = logging.getLogger(__name__)

KEY_INDEX = "sms-pendente:por_tempo"


def chave_hash(id_externo: str) -> str:
    return f"sms-pendente:{id_externo}"


class RepositorioSmsPendenteRedis:
    async def criar(
        self,
        redis: Redis,
        *,
        id_externo: str,
        telefone: str,
        tipo_template: str,
        contexto: dict[str, str],
        remetente: str | None,
        origem: str,
        fornecedor_id: str | None = None,
        cnpj_basico: str | None = None,
        consulta_id: uuid.UUID | None = None,
        sobrescrever_trava_de_email_esperando: bool = False,
    ) -> bool:
        key = chave_hash(id_externo)
        reservou_trava = False
        if sobrescrever_trava_de_email_esperando:
            await redefinir_para_pendente_sms_pos_bounce(
                redis, consulta_id, cnpj_basico, id_externo
            )
        elif consulta_id is not None:
            if not await tentar_travar_pendente_sms(
                redis, consulta_id, cnpj_basico, id_externo
            ):
                raise ConsultaJaNotificadaError(f"{consulta_id}:{cnpj_basico or ''}")
            reservou_trava = True
        try:
            if await redis.exists(key):
                if reservou_trava:
                    await liberar_trava_forcado(redis, consulta_id, cnpj_basico)
                return False
            agora = int(time.time())
            mapping: dict[str, str] = {
                "id_externo": id_externo,
                "telefone": telefone,
                "tipo_template": tipo_template,
                "contexto_json": json.dumps(contexto, ensure_ascii=False),
                "remetente": remetente or "",
                "origem": origem,
                "fornecedor_id": fornecedor_id or "",
                "cnpj_basico": cnpj_basico or "",
                "consulta_id": str(consulta_id) if consulta_id is not None else "",
                "criado_em": str(agora),
            }
            pipe = redis.pipeline(transaction=True)
            pipe.hset(key, mapping=mapping)
            pipe.zadd(KEY_INDEX, {id_externo: float(agora)})
            await pipe.execute()
        except Exception:
            if reservou_trava:
                await liberar_trava_forcado(redis, consulta_id, cnpj_basico)
            raise
        _log.info("SMS na fila Redis (sms-pendente): id_externo=%s origem=%s", id_externo, origem)
        return True

    async def remover(self, redis: Redis, id_externo: str) -> None:
        key = chave_hash(id_externo)
        raw = await redis.hgetall(key)
        cid_raw = (raw.get("consulta_id") or "").strip() if raw else ""
        cnpj_lo = (raw.get("cnpj_basico") or "").strip() if raw else ""
        consulta_uuid: uuid.UUID | None = None
        if cid_raw:
            try:
                consulta_uuid = uuid.UUID(cid_raw)
            except ValueError:
                consulta_uuid = None
        pipe = redis.pipeline(transaction=True)
        pipe.delete(key)
        pipe.zrem(KEY_INDEX, id_externo)
        await pipe.execute()
        await liberar_trava_se_fase(
            redis,
            consulta_uuid,
            cnpj_lo or None,
            fase_pendente_sms(id_externo),
        )

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
                    "id_externo": raw.get("id_externo") or raw.get("external_id", ext),
                    "telefone": raw.get("telefone", ""),
                    "tipo_template": raw.get("tipo_template", ""),
                    "contexto": ctx if isinstance(ctx, dict) else {},
                    "remetente": raw.get("remetente") or None,
                    "origem": raw.get("origem", ""),
                    "fornecedor_id": raw.get("fornecedor_id") or raw.get("usuario_id") or None,
                    "cnpj_basico": raw.get("cnpj_basico") or None,
                    "consulta_id": raw.get("consulta_id") or None,
                    "criado_em": raw.get("criado_em"),
                },
            )
        return saida

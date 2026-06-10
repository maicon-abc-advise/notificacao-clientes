"""Fila Redis: ligações ainda **não** disparadas (consumidor remove após dispatch).

Chaves (namespace ``ligacoes-pendente``):
- ``ligacoes-pendente:{id_externo}`` — hash com payload para ``POST /v1/calls/dispatch``.
- ``ligacoes-pendente:por_tempo`` — sorted set (score = epoch) para listar por ordem.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from redis.asyncio import Redis

_log = logging.getLogger(__name__)

KEY_INDEX = "ligacoes-pendente:por_tempo"


def chave_hash(id_externo: str) -> str:
    return f"ligacoes-pendente:{id_externo}"


class RepositorioLigacoesPendenteRedis:
    async def criar(
        self,
        redis: Redis,
        *,
        id_externo: str,
        telefone: str,
        cnpj_basico: str,
        quantidade_buscas: int,
        uf_buscada: str,
        segmento_buscado: str,
        origem: str,
        nome_empresa: str | None = None,
        fornecedor_id: str | None = None,
    ) -> bool:
        key = chave_hash(id_externo)
        if await redis.exists(key):
            return False
        agora = int(time.time())
        mapping: dict[str, str] = {
            "id_externo": id_externo,
            "telefone": telefone,
            "cnpj_basico": cnpj_basico,
            "quantidade_buscas": str(quantidade_buscas),
            "uf_buscada": uf_buscada,
            "segmento_buscado": segmento_buscado,
            "origem": origem,
            "nome_empresa": nome_empresa or "",
            "fornecedor_id": fornecedor_id or "",
            "criado_em": str(agora),
        }
        pipe = redis.pipeline(transaction=True)
        pipe.hset(key, mapping=mapping)
        pipe.zadd(KEY_INDEX, {id_externo: float(agora)})
        await pipe.execute()
        _log.info("Ligação na fila Redis (ligacoes-pendente): id_externo=%s origem=%s", id_externo, origem)
        return True

    async def remover(self, redis: Redis, id_externo: str) -> None:
        key = chave_hash(id_externo)
        pipe = redis.pipeline(transaction=True)
        pipe.delete(key)
        pipe.zrem(KEY_INDEX, id_externo)
        await pipe.execute()

    async def listar_pendentes(self, redis: Redis, *, limite: int = 200) -> list[dict[str, Any]]:
        ids = await redis.zrange(KEY_INDEX, 0, limite - 1)
        return await self._carregar_itens_por_ids(redis, ids)

    async def listar_pendentes_recentes(self, redis: Redis, *, limite: int = 200) -> list[dict[str, Any]]:
        ids = await redis.zrevrange(KEY_INDEX, 0, limite - 1)
        return await self._carregar_itens_por_ids(redis, ids)

    async def obter_hash(self, redis: Redis, id_externo: str) -> dict[str, str] | None:
        key = chave_hash(id_externo)
        raw = await redis.hgetall(key)
        if not raw:
            return None
        return {k.decode() if isinstance(k, bytes) else str(k): (v.decode() if isinstance(v, bytes) else str(v)) for k, v in raw.items()}

    async def _carregar_itens_por_ids(self, redis: Redis, ids: list[str | bytes]) -> list[dict[str, Any]]:
        saida: list[dict[str, Any]] = []
        for ext in ids:
            ext_s = ext.decode() if isinstance(ext, bytes) else str(ext)
            raw = await redis.hgetall(chave_hash(ext_s))
            if not raw:
                await redis.zrem(KEY_INDEX, ext_s)
                continue
            item = _hash_para_dict(raw, ext_s)
            if item:
                saida.append(item)
        return saida


def _h(raw: dict[Any, Any], key: str) -> str:
    for rk, rv in raw.items():
        ks = rk.decode() if isinstance(rk, bytes) else str(rk)
        if ks != key:
            continue
        if rv is None:
            return ""
        if isinstance(rv, bytes):
            return rv.decode(errors="replace")
        return str(rv)
    return ""


def _hash_para_dict(raw: dict[Any, Any], ext_s: str) -> dict[str, Any] | None:
    qtd_raw = _h(raw, "quantidade_buscas")
    try:
        quantidade_buscas = int(qtd_raw) if qtd_raw else 0
    except ValueError:
        quantidade_buscas = 0
    fid = _h(raw, "fornecedor_id") or None
    try:
        if fid:
            uuid.UUID(fid)
    except ValueError:
        fid = None
    return {
        "id_externo": _h(raw, "id_externo") or ext_s,
        "telefone": _h(raw, "telefone"),
        "cnpj_basico": _h(raw, "cnpj_basico") or None,
        "quantidade_buscas": quantidade_buscas,
        "uf_buscada": _h(raw, "uf_buscada") or None,
        "segmento_buscado": _h(raw, "segmento_buscado") or None,
        "nome_empresa": _h(raw, "nome_empresa") or None,
        "fornecedor_id": fid,
        "origem": _h(raw, "origem"),
        "criado_em": _h(raw, "criado_em") or None,
    }

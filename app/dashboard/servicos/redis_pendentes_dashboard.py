"""Carregamento em lote de pendentes Redis para o dashboard (pipeline)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from redis.asyncio import Redis

from app.reenvio.servicos.n8n_claims import chave_claim_n8n


def _id_str(valor: Any) -> str:
    return valor.decode() if isinstance(valor, bytes) else str(valor)


async def carregar_pendentes_redis_em_lote(
    redis: Redis,
    *,
    ids_raw: list[Any],
    chave_hash_fn: Callable[[str], str],
    canal: str,
) -> list[tuple[str, dict[Any, Any] | None, bool]]:
    """``hgetall`` + ``exists`` (claim) em 2 pipelines em vez de 2×N round-trips."""
    ids = [_id_str(ext) for ext in ids_raw]
    if not ids:
        return []

    pipe_dados = redis.pipeline(transaction=False)
    for ext_s in ids:
        pipe_dados.hgetall(chave_hash_fn(ext_s))
    hashes = await pipe_dados.execute()

    pipe_claims = redis.pipeline(transaction=False)
    for ext_s in ids:
        pipe_claims.exists(chave_claim_n8n(canal, ext_s))
    claims = await pipe_claims.execute()

    return [
        (ext_s, hashes[i] or None, bool(claims[i]))
        for i, ext_s in enumerate(ids)
    ]


async def remover_fantasmas_indice(
    redis: Redis,
    *,
    idx_key: str,
    ids: list[str],
) -> None:
    if not ids:
        return
    await redis.zrem(idx_key, *ids)

"""Remove da fila Redis itens que já constam em ``emails_enviados`` (pós-envio)."""

from __future__ import annotations

import logging

import asyncpg
from redis.asyncio import Redis

from app.mensageria.repositorios.postgres_emails_enviados import buscar_enviados_por_ids_externos
from app.orquestracao.repositorios.redis_emails_pendentes_repo import (
    KEY_INDEX,
    RepositorioEmailsPendenteRedis,
)

_log = logging.getLogger(__name__)


async def executar_limpar_emails_pendentes_ja_enviados(
    pool: asyncpg.Pool,
    redis: Redis,
    *,
    limite: int = 500,
) -> dict:
    """Varre pendentes no Redis e remove os que já foram enviados (Postgres)."""
    limite_efetivo = max(1, min(limite, 5000))
    ids_pendentes = await redis.zrange(KEY_INDEX, 0, limite_efetivo - 1)
    candidatos = len(ids_pendentes)
    if not ids_pendentes:
        return {"candidatos_pendentes": 0, "removidos": 0, "itens": []}

    enviados = await buscar_enviados_por_ids_externos(pool, list(ids_pendentes))
    por_id_externo = {str(row["id_externo"]): row for row in enviados}

    repo = RepositorioEmailsPendenteRedis()
    removidos: list[dict[str, str | None]] = []
    for id_externo in ids_pendentes:
        row = por_id_externo.get(id_externo)
        if row is None:
            continue
        await repo.remover(redis, id_externo)
        item = {
            "id_externo": id_externo,
            "cnpj_basico": str(row["cnpj_basico"]).strip() if row["cnpj_basico"] else None,
            "id_mensagem_zenvia": str(row["id_mensagem_zenvia"]).strip()
            if row["id_mensagem_zenvia"]
            else None,
        }
        removidos.append(item)
        _log.info(
            "Limpeza pendentes: removido id_externo=%s cnpj_basico=%s id_mensagem_zenvia=%s",
            id_externo,
            item["cnpj_basico"] or "",
            item["id_mensagem_zenvia"] or "",
        )

    return {
        "candidatos_pendentes": candidatos,
        "removidos": len(removidos),
        "itens": removidos,
    }

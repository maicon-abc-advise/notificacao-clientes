"""Backfill de variante A/B nos e-mails pendentes no Redis."""

from __future__ import annotations

import logging
from typing import Any

from redis.asyncio import Redis

from app.experimentos.growthbook_servico import resolver_variante_email_busca
from app.experimentos.variante_email import normalizar_variante
from app.orquestracao.repositorios.redis_emails_pendentes_repo import (
    KEY_INDEX,
    chave_hash,
)
from app.templates.modelo import CodigoTipoTemplate

_log = logging.getLogger(__name__)

_TIPOS_EMAIL_BUSCA = frozenset(
    {
        CodigoTipoTemplate.APARECEU_BUSCA,
        CodigoTipoTemplate.APARECEU_BUSCA_SEM_REGISTRO,
    }
)


def _h(raw: dict[Any, Any], key: str) -> str | None:
    if not raw:
        return None
    for rk, rv in raw.items():
        ks = rk.decode() if isinstance(rk, bytes) else str(rk)
        if ks != key:
            continue
        if rv is None:
            return None
        return rv.decode() if isinstance(rv, bytes) else str(rv)
    return None


def _variante_ja_definida(raw: dict[Any, Any]) -> bool:
    return bool((_h(raw, "variante") or "").strip())


def _parse_tipo_template(valor: str | None) -> CodigoTipoTemplate | None:
    v = (valor or "").strip()
    if not v:
        return None
    try:
        return CodigoTipoTemplate(v)
    except ValueError:
        return None


async def decidir_variantes_email_pendentes(redis: Redis) -> dict[str, int]:
    """Preenche ``variante`` e ``experimento_id`` nos pendentes que ainda não têm variante."""
    stats = {
        "total_analisados": 0,
        "atualizados": 0,
        "ja_tinham_variante": 0,
        "simples": 0,
        "elaborado": 0,
        "ignorados_tipo": 0,
        "erros": 0,
    }

    ids_raw = await redis.zrevrange(KEY_INDEX, 0, -1)
    for ext in ids_raw:
        ext_s = ext.decode() if isinstance(ext, bytes) else str(ext)
        stats["total_analisados"] += 1
        raw = await redis.hgetall(chave_hash(ext_s))
        if not raw:
            await redis.zrem(KEY_INDEX, ext_s)
            stats["total_analisados"] -= 1
            continue

        if _variante_ja_definida(raw):
            stats["ja_tinham_variante"] += 1
            continue

        tipo = _parse_tipo_template(_h(raw, "tipo_template"))
        if tipo is None or tipo not in _TIPOS_EMAIL_BUSCA:
            stats["ignorados_tipo"] += 1
            continue

        cnpj = (_h(raw, "cnpj_basico") or "").strip() or None
        try:
            variante, experimento_id = await resolver_variante_email_busca(
                cnpj,
                tipo_template=tipo,
            )
        except Exception:
            _log.exception("Falha ao decidir variante id_externo=%s", ext_s)
            stats["erros"] += 1
            continue

        var = normalizar_variante(variante)
        exp = (experimento_id or "").strip()
        await redis.hset(
            chave_hash(ext_s),
            mapping={
                "variante": var,
                "experimento_id": exp,
            },
        )
        stats["atualizados"] += 1
        if var == "elaborado":
            stats["elaborado"] += 1
        else:
            stats["simples"] += 1
        _log.info(
            "Variante definida no pendente id_externo=%s variante=%s experimento_id=%s",
            ext_s,
            var,
            exp or None,
        )

    return stats

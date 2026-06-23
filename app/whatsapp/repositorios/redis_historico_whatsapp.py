"""Histórico de conversa WhatsApp no Redis principal (listas n8n ``{numero}@s.whatsapp.net``)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from app.reenvio.redis_app import obter_cliente_redis
from app.whatsapp.api.externo.evolution.adaptador_evolution import jid_whatsapp
from app.whatsapp.servicos.telefone_whatsapp import variantes_telefone_whatsapp

_log = logging.getLogger(__name__)

_AGENT_PREFIX = re.compile(r"^Agent:\s*", re.IGNORECASE)
_FORNECEDOR_PREFIX = re.compile(r"^(Fornecedor|Cliente|User):\s*", re.IGNORECASE)


def jid_historico_whatsapp(numero: str) -> str:
    return jid_whatsapp(numero)


def _parse_entrada_n8n(linha: str, remote_jid: str) -> dict | None:
    texto = linha.strip()
    if not texto:
        return None
    from_me = bool(_AGENT_PREFIX.match(texto))
    if from_me:
        texto = _AGENT_PREFIX.sub("", texto, count=1).strip()
    else:
        texto = _FORNECEDOR_PREFIX.sub("", texto, count=1).strip()
    if not texto:
        return None
    return {
        "key": {"fromMe": from_me, "remoteJid": remote_jid},
        "message": {"conversation": texto},
        "source": "redis_n8n",
    }


def parse_lista_redis_n8n(raw_items: list[str], remote_jid: str) -> list[dict]:
    """Converte LRANGE em mensagens no formato Evolution (ordem cronológica)."""
    mensagens: list[dict] = []
    for item in reversed(raw_items):
        msg = _parse_entrada_n8n(item, remote_jid)
        if msg:
            mensagens.append(msg)
    return mensagens


@dataclass
class RedisHistoricoResult:
    messages: list[dict]
    redis_key: str | None
    variantes_tentadas: list[str]
    raw_total: int

    def debug_dict(self) -> dict[str, Any]:
        return {
            "redis_key": self.redis_key,
            "redis_variantes_tentadas": self.variantes_tentadas,
            "redis_mensagens_raw": self.raw_total,
        }


async def buscar_historico_redis_n8n(telefone: str) -> RedisHistoricoResult:
    """LRANGE na lista n8n; tenta variantes com/sem 9 no DDD."""
    try:
        sem_nove, com_nove = variantes_telefone_whatsapp(telefone)
    except ValueError as exc:
        _log.warning("Telefone inválido para histórico Redis: %s", exc)
        return RedisHistoricoResult([], None, [], 0)

    variantes = [com_nove, sem_nove]
    keys_tentadas = [jid_historico_whatsapp(v) for v in variantes]
    redis = await obter_cliente_redis()

    for key in keys_tentadas:
        try:
            raw = await redis.lrange(key, 0, -1)
        except Exception as exc:
            _log.warning("Falha LRANGE Redis key=%s: %s", key, exc)
            continue
        if raw:
            messages = parse_lista_redis_n8n(raw, key)
            _log.info(
                "Histórico Redis n8n key=%s itens=%s mensagens=%s",
                key,
                len(raw),
                len(messages),
            )
            return RedisHistoricoResult(messages, key, keys_tentadas, len(raw))

    return RedisHistoricoResult([], None, keys_tentadas, 0)

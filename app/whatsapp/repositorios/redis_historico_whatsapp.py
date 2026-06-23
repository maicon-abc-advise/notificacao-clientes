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


def formatar_linha_agente_historico(texto: str) -> str:
    """Linha no formato n8n para mensagem da Cláudia (``fromMe=true`` no parser)."""
    return f"Agent: {(texto or '').strip()}"


def _par_chaves_historico(telefone: str) -> tuple[str, str, list[str]]:
    """
    Chave canônica = variante que coincide com os dígitos do telefone no banco.
    Chave alternativa = outra variante com/sem 9 no celular.
    """
    sem_nove, com_nove = variantes_telefone_whatsapp(telefone)
    key_sem = jid_historico_whatsapp(sem_nove)
    key_com = jid_historico_whatsapp(com_nove)
    digits_raw = "".join(ch for ch in telefone if ch.isdigit())
    if digits_raw == com_nove:
        key_canon, key_alt = key_com, key_sem
    elif digits_raw == sem_nove:
        key_canon, key_alt = key_sem, key_com
    else:
        key_canon, key_alt = key_sem, key_com
    return key_canon, key_alt, [key_canon, key_alt]


def _merge_historico_duas_listas(msgs_canon: list[dict], msgs_alt: list[dict]) -> list[dict]:
    """Une históricos partidos entre variantes com/sem 9 (dedup + ordem heurística)."""
    if not msgs_alt:
        return msgs_canon
    if not msgs_canon:
        return msgs_alt

    seen = {(m["key"]["fromMe"], m["message"]["conversation"]) for m in msgs_canon}
    alt_only = [m for m in msgs_alt if (m["key"]["fromMe"], m["message"]["conversation"]) not in seen]
    prepend = [m for m in alt_only if m["key"]["fromMe"]]
    append = [m for m in alt_only if not m["key"]["fromMe"]]
    return prepend + msgs_canon + append


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
    """LRANGE nas variantes com/sem 9 e une o histórico quando ambas tiverem itens."""
    try:
        key_canon, key_alt, keys_tentadas = _par_chaves_historico(telefone)
    except ValueError as exc:
        _log.warning("Telefone inválido para histórico Redis: %s", exc)
        return RedisHistoricoResult([], None, [], 0)

    redis = await obter_cliente_redis()
    raw_por_chave: dict[str, list[str]] = {}

    for key in (key_canon, key_alt):
        try:
            raw = await redis.lrange(key, 0, -1)
        except Exception as exc:
            _log.warning("Falha LRANGE Redis key=%s: %s", key, exc)
            continue
        if raw:
            raw_por_chave[key] = raw

    if not raw_por_chave:
        return RedisHistoricoResult([], None, keys_tentadas, 0)

    msgs_canon = parse_lista_redis_n8n(raw_por_chave.get(key_canon, []), key_canon)
    msgs_alt = parse_lista_redis_n8n(raw_por_chave.get(key_alt, []), key_alt)
    messages = _merge_historico_duas_listas(msgs_canon, msgs_alt)
    raw_total = sum(len(raw) for raw in raw_por_chave.values())
    redis_key = key_canon

    _log.info(
        "Histórico Redis n8n keys=%s itens=%s mensagens=%s",
        list(raw_por_chave),
        raw_total,
        len(messages),
    )
    return RedisHistoricoResult(messages, redis_key, keys_tentadas, raw_total)


async def append_mensagem_agente_historico_redis(telefone: str, texto: str) -> str | None:
    """
    Grava mensagem outbound na chave canônica (dígitos do telefone como no banco).

    Usa ``LPUSH`` e prefixo ``Agent:`` — compatível com ``parse_lista_redis_n8n``.
    """
    conteudo = (texto or "").strip()
    if not conteudo:
        return None
    try:
        key_canon, _, _ = _par_chaves_historico(telefone)
    except ValueError as exc:
        _log.warning("Telefone inválido para gravar histórico Redis: %s", exc)
        return None

    linha = formatar_linha_agente_historico(conteudo)
    redis = await obter_cliente_redis()
    try:
        await redis.lpush(key_canon, linha)
    except Exception as exc:
        _log.warning("Falha LPUSH histórico Redis key=%s: %s", key_canon, exc)
        return None
    _log.info("Histórico Redis agente gravado key=%s chars=%s", key_canon, len(conteudo))
    return key_canon

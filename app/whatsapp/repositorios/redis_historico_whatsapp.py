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


def _chave_historico_whatsapp(telefone: str) -> str:
    """Chave única = dígitos do telefone como no banco + ``@s.whatsapp.net``."""
    sem_nove, com_nove = variantes_telefone_whatsapp(telefone)
    digits_raw = "".join(ch for ch in telefone if ch.isdigit())
    if digits_raw == com_nove:
        digits = com_nove
    elif digits_raw == sem_nove:
        digits = sem_nove
    else:
        digits = sem_nove
    return jid_historico_whatsapp(digits)


def _chaves_variantes_historico(telefone: str) -> tuple[str, str, str]:
    """Retorna ``(chave_registro, chave_sem_nove, chave_com_nove)``."""
    sem_nove, com_nove = variantes_telefone_whatsapp(telefone)
    key_sem = jid_historico_whatsapp(sem_nove)
    key_com = jid_historico_whatsapp(com_nove)
    key_registro = _chave_historico_whatsapp(telefone)
    return key_registro, key_sem, key_com


def ordem_cronologica_lista_n8n(raw: list[str]) -> list[str]:
    """n8n grava com ``LPUSH``; ``LRANGE 0 -1`` retorna do mais novo ao mais antigo."""
    return list(reversed(raw))


def mesclar_raw_historico_variantes(
    raw_registro: list[str],
    raw_outra: list[str],
) -> list[str]:
    """
    Une listas de duas chaves ``@s.whatsapp.net`` (com/sem 9).

    ``raw_registro`` vem da API (``RPUSH``, já cronológico).
    ``raw_outra`` deve vir normalizado via ``ordem_cronologica_lista_n8n``.

    - Só uma com dados: retorna essa.
    - Uma com 1 item e outra com vários: a de 1 item vem primeiro.
    - Ambas com 2+ ou ambas com 1 distinta: ``registro + outra``.
    - Ambas com 1 idêntica: deduplica.
    """
    if not raw_registro and not raw_outra:
        return []
    if raw_registro and not raw_outra:
        return list(raw_registro)
    if raw_outra and not raw_registro:
        return list(raw_outra)

    len_r, len_o = len(raw_registro), len(raw_outra)
    if len_r == 1 and len_o > 1:
        return list(raw_registro) + list(raw_outra)
    if len_o == 1 and len_r > 1:
        return list(raw_outra) + list(raw_registro)
    if len_r == 1 and len_o == 1 and raw_registro[0] == raw_outra[0]:
        return list(raw_registro)
    return list(raw_registro) + list(raw_outra)


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
    """Converte LRANGE (RPUSH) em mensagens no formato Evolution (ordem cronológica)."""
    mensagens: list[dict] = []
    for item in raw_items:
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
    raw_por_chave: dict[str, int] | None = None

    def debug_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "redis_key": self.redis_key,
            "redis_variantes_tentadas": self.variantes_tentadas,
            "redis_mensagens_raw": self.raw_total,
        }
        if self.raw_por_chave:
            out["redis_mensagens_raw_por_chave"] = self.raw_por_chave
        return out


async def buscar_historico_redis_n8n(telefone: str) -> RedisHistoricoResult:
    """LRANGE nas variantes com/sem 9 e mescla quando o histórico está dividido."""
    try:
        key_registro, key_sem, key_com = _chaves_variantes_historico(telefone)
    except ValueError as exc:
        _log.warning("Telefone inválido para histórico Redis: %s", exc)
        return RedisHistoricoResult([], None, [], 0)

    variantes = [key_sem, key_com]
    key_outra = key_com if key_registro == key_sem else key_sem

    redis = await obter_cliente_redis()
    raw_registro: list[str] = []
    raw_outra: list[str] = []
    try:
        raw_registro = await redis.lrange(key_registro, 0, -1)
        raw_outra = await redis.lrange(key_outra, 0, -1)
    except Exception as exc:
        _log.warning(
            "Falha LRANGE Redis keys=%s/%s: %s",
            key_registro,
            key_outra,
            exc,
        )
        return RedisHistoricoResult([], key_registro, variantes, 0)

    raw_por_chave = {key_registro: len(raw_registro), key_outra: len(raw_outra)}
    if not raw_registro and not raw_outra:
        return RedisHistoricoResult([], None, variantes, 0, raw_por_chave)

    raw_outra_cronologico = ordem_cronologica_lista_n8n(raw_outra)
    mesclado = mesclar_raw_historico_variantes(raw_registro, raw_outra_cronologico)
    redis_key = key_registro if raw_registro else key_outra
    if raw_registro and raw_outra:
        redis_key = key_registro

    messages = parse_lista_redis_n8n(mesclado, redis_key)
    _log.info(
        "Histórico Redis n8n registro=%s outra=%s itens=%s mensagens=%s",
        len(raw_registro),
        len(raw_outra),
        len(mesclado),
        len(messages),
    )
    return RedisHistoricoResult(
        messages,
        redis_key,
        variantes,
        len(mesclado),
        raw_por_chave,
    )


async def append_mensagem_agente_historico_redis(telefone: str, texto: str) -> str | None:
    """
    Grava mensagem outbound na chave do telefone (dígitos como no banco).

    Usa ``RPUSH`` e prefixo ``Agent:`` (n8n externo usa ``LPUSH`` na chave complementar).
    """
    conteudo = (texto or "").strip()
    if not conteudo:
        return None
    try:
        redis_key = _chave_historico_whatsapp(telefone)
    except ValueError as exc:
        _log.warning("Telefone inválido para gravar histórico Redis: %s", exc)
        return None

    linha = formatar_linha_agente_historico(conteudo)
    redis = await obter_cliente_redis()
    try:
        await redis.rpush(redis_key, linha)
    except Exception as exc:
        _log.warning("Falha RPUSH histórico Redis key=%s: %s", redis_key, exc)
        return None
    _log.info("Histórico Redis agente gravado key=%s chars=%s", redis_key, len(conteudo))
    return redis_key

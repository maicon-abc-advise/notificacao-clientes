"""Fila externa ``contato-fornecedores`` (Redis dedicado, legado whatsapp-suppliers-dashboard)."""

from __future__ import annotations

import asyncio
import logging

from redis.asyncio import Redis

from app.config.config import Configuracao
from app.whatsapp.servicos.telefone_whatsapp import variantes_telefone_whatsapp

_log = logging.getLogger(__name__)

CONTATO_FORNECEDORES_KEY = "contato-fornecedores"

_cliente: Redis | None = None
_url_ativa: str | None = None
_lock = asyncio.Lock()


async def _obter_cliente(url: str) -> Redis:
    global _cliente, _url_ativa
    async with _lock:
        if _cliente is None or _url_ativa != url:
            if _cliente is not None:
                await _cliente.aclose()
            _cliente = Redis.from_url(url, decode_responses=True)
            _url_ativa = url
            _log.debug("Cliente Redis contato-fornecedores inicializado")
    return _cliente


async def fechar_cliente_contato_fornecedores() -> None:
    global _cliente, _url_ativa
    async with _lock:
        if _cliente is not None:
            await _cliente.aclose()
            _cliente = None
            _url_ativa = None


async def enfileirar_contato_fornecedor(cfg: Configuracao, telefone: str) -> list[str] | None:
    """
    LPUSH das variantes com/sem 9 na lista ``contato-fornecedores``.
    Retorna ``None`` se ``REDIS_CONTATO_FORNECEDORES_URL*`` não estiver configurada.
    """
    url = (cfg.redis_contato_fornecedores_url or "").strip()
    if not url:
        return None

    sem_nove, com_nove = variantes_telefone_whatsapp(telefone)
    redis = await _obter_cliente(url)
    await redis.lpush(CONTATO_FORNECEDORES_KEY, com_nove, sem_nove)
    _log.info(
        "contato-fornecedores enfileirado: %s, %s (key=%s)",
        com_nove,
        sem_nove,
        CONTATO_FORNECEDORES_KEY,
    )
    return [sem_nove, com_nove]

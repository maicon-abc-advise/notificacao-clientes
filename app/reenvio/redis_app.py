import asyncio
import logging
from redis.asyncio import Redis
from app.config.config import obter_configuracao

_log = logging.getLogger(__name__)
_cliente: Redis | None = None
_lock = asyncio.Lock()

async def obter_cliente_redis() -> Redis:
    global _cliente
    async with _lock:
        if _cliente is None:
            cfg = obter_configuracao()
            _cliente = Redis.from_url(cfg.redis_url, decode_responses=True)
            _log.debug("Cliente Redis inicializado")
    return _cliente

async def fechar_cliente_redis() -> None:
    global _cliente
    async with _lock:
        if _cliente is not None:
            await _cliente.aclose()
            _cliente = None
            _log.debug("Cliente Redis encerrado")

import asyncio

import asyncpg

from app.config.config import obter_configuracao

_pool: asyncpg.Pool | None = None
_lock = asyncio.Lock()


async def obter_pool() -> asyncpg.Pool:
    global _pool
    async with _lock:
        if _pool is None:
            cfg = obter_configuracao()
            _pool = await asyncpg.create_pool(cfg.database_url, min_size=1, max_size=5)
    return _pool


async def fechar_pool() -> None:
    global _pool
    async with _lock:
        if _pool is not None:
            await _pool.close()
            _pool = None

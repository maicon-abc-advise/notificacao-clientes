import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.whatsapp.repositorios import postgres_whatsapp_envios as repo


async def _test_listar_pendentes_sem_limite_ordena_asc() -> None:
    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=[])
    await repo.listar_pendentes_para_envio(pool)
    sql = pool.fetch.call_args.args[0]
    assert "updated_at ASC" in sql
    assert "LIMIT" not in sql
    assert pool.fetch.call_args.args[1:] == ()


async def _test_listar_pendentes_com_limite_ordena_desc() -> None:
    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=[])
    await repo.listar_pendentes_para_envio(pool, limite=5)
    sql = pool.fetch.call_args.args[0]
    assert "updated_at DESC" in sql
    assert "LIMIT $1" in sql
    assert pool.fetch.call_args.args[1] == 5


def test_listar_pendentes_limite() -> None:
    asyncio.run(_test_listar_pendentes_sem_limite_ordena_asc())
    asyncio.run(_test_listar_pendentes_com_limite_ordena_desc())

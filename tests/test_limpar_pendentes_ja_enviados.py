from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from app.reenvio.servicos.limpar_pendentes_ja_enviados import (
    executar_limpar_emails_pendentes_ja_enviados,
)


def test_limpar_remove_pendentes_que_ja_estao_em_enviados() -> None:
    asyncio.run(_test_limpar_remove_pendentes_que_ja_estao_em_enviados())


async def _test_limpar_remove_pendentes_que_ja_estao_em_enviados() -> None:
    redis = AsyncMock()
    redis.zrange = AsyncMock(return_value=["ext-enviado", "ext-pendente"])
    pool = AsyncMock()

    enviados = [
        {
            "id_externo": "ext-enviado",
            "id_mensagem_zenvia": "zenvia-123",
            "cnpj_basico": "12345678",
        }
    ]
    repo = AsyncMock()
    repo.remover = AsyncMock()

    with (
        patch(
            "app.reenvio.servicos.limpar_pendentes_ja_enviados.buscar_enviados_por_ids_externos",
            AsyncMock(return_value=enviados),
        ),
        patch(
            "app.reenvio.servicos.limpar_pendentes_ja_enviados.RepositorioEmailsPendenteRedis",
            return_value=repo,
        ),
    ):
        out = await executar_limpar_emails_pendentes_ja_enviados(pool, redis, limite=500)

    assert out["candidatos_pendentes"] == 2
    assert out["removidos"] == 1
    assert out["itens"] == [
        {
            "id_externo": "ext-enviado",
            "cnpj_basico": "12345678",
            "id_mensagem_zenvia": "zenvia-123",
        }
    ]
    repo.remover.assert_awaited_once_with(redis, "ext-enviado")


def test_limpar_sem_pendentes_retorna_vazio() -> None:
    asyncio.run(_test_limpar_sem_pendentes_retorna_vazio())


async def _test_limpar_sem_pendentes_retorna_vazio() -> None:
    redis = AsyncMock()
    redis.zrange = AsyncMock(return_value=[])
    pool = AsyncMock()

    out = await executar_limpar_emails_pendentes_ja_enviados(pool, redis)

    assert out == {"candidatos_pendentes": 0, "removidos": 0, "itens": []}

"""Testes da fila Redis contato-fornecedores."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.config.config import Configuracao, obter_configuracao
from app.whatsapp.repositorios.redis_contato_fornecedores import (
    CONTATO_FORNECEDORES_KEY,
    enfileirar_contato_fornecedor,
)


def test_enfileirar_contato_fornecedor_lpush_variantes(monkeypatch) -> None:
    monkeypatch.setenv("REDIS_CONTATO_FORNECEDORES_URL", "redis://localhost:6379/1")
    obter_configuracao.cache_clear()
    cfg = obter_configuracao()

    mock_redis = AsyncMock()
    mock_redis.lpush = AsyncMock(return_value=2)

    async def _run() -> list[str] | None:
        with patch(
            "app.whatsapp.repositorios.redis_contato_fornecedores._obter_cliente",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            return await enfileirar_contato_fornecedor(cfg, "11948993785")

    out = asyncio.run(_run())
    assert out == ["551148993785", "5511948993785"]
    mock_redis.lpush.assert_awaited_once_with(
        CONTATO_FORNECEDORES_KEY,
        "5511948993785",
        "551148993785",
    )


def test_enfileirar_contato_fornecedor_sem_url_retorna_none() -> None:
    cfg = MagicMock(spec=Configuracao)
    cfg.redis_contato_fornecedores_url = ""
    assert asyncio.run(enfileirar_contato_fornecedor(cfg, "11948993785")) is None

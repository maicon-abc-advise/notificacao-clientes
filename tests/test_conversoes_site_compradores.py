"""Testes das métricas de conversão site (shortlinks → comprador)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.dashboard.servicos import conversoes_site_compradores_servico as servico


def test_contar_metricas_conversoes_site(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = AsyncMock()
    pool.fetchrow.return_value = {"shortlinks_site": 10, "conversoes": 3}

    p = MagicMock()
    p.qual.side_effect = lambda base: {
        "consulta_shortlinks": "public.consulta_shortlinks",
        "consultas": "busca_fornecedor.consultas",
        "usuario_comprador": "busca_fornecedor.usuario_comprador",
    }[base]
    monkeypatch.setattr(servico, "obter_identificadores_postgres", lambda: p)

    shortlinks, conversoes = asyncio.run(servico.contar_metricas_conversoes_site(pool, None))

    assert shortlinks == 10
    assert conversoes == 3
    sql = pool.fetchrow.call_args[0][0]
    assert "public.consulta_shortlinks" in sql
    assert "origem" in sql
    assert "comprador_id IS NULL" in sql


def test_listar_conversoes_site_apenas_convertidos(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = AsyncMock()
    pool.fetchval.return_value = 1
    pool.fetch.return_value = [
        {
            "shortlink_id": "sl-1",
            "shortlink_code": "ABC12345",
            "shortlink_criado_em": datetime(2026, 7, 1, tzinfo=timezone.utc),
            "view_count": 2,
            "consulta_id": "c-1",
            "comprador_id": "u-1",
            "comprador_nome": "Maria",
            "empresa_nome": "Empresa X",
            "comprador_cadastrado_em": datetime(2026, 7, 2, tzinfo=timezone.utc),
            "converteu": True,
        }
    ]

    p = MagicMock()
    p.qual.side_effect = lambda base: {
        "consulta_shortlinks": "public.consulta_shortlinks",
        "consultas": "busca_fornecedor.consultas",
        "usuario_comprador": "busca_fornecedor.usuario_comprador",
    }[base]
    monkeypatch.setattr(servico, "obter_identificadores_postgres", lambda: p)

    itens, total = asyncio.run(
        servico.listar_conversoes_site_compradores(
            pool,
            page=1,
            page_size=10,
            periodo=None,
            apenas_convertidos=True,
        )
    )

    assert total == 1
    assert len(itens) == 1
    assert itens[0]["converteu"] is True
    assert itens[0]["estado_exibicao"]["rotulo"] == "Convertido"
    sql_list = pool.fetch.call_args[0][0]
    assert "NOT" not in sql_list.split("WHERE")[-1]

"""Testes de conversão de compradores por acesso (usuario_comprador.n_acessos)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.orquestracao.repositorios import engajamento_compradores_repo as repo
from app.orquestracao.servicos import sincronizar_conversoes_compradores_servico as servico


def test_marcar_convertido_por_telefone_vazio() -> None:
    out = asyncio.run(repo.marcar_convertido_por_telefone(AsyncMock(), telefone=""))
    assert out is False


def test_marcar_convertido_por_telefone_atualiza(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value={"telefone": "5511999999999"})

    monkeypatch.setattr(
        repo,
        "obter_identificadores_postgres",
        lambda: type("P", (), {"qual": lambda self, b: f"public.{b}"})(),
    )

    out = asyncio.run(repo.marcar_convertido_por_telefone(pool, telefone="5511999999999"))
    assert out is True
    pool.fetchrow.assert_awaited_once()
    sql = pool.fetchrow.await_args.args[0]
    assert "converteu = true" in sql
    assert "primeira_consulta_sem_cadastro = true" in sql


def test_sincronizar_conversoes_usa_n_acessos(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = AsyncMock()
    pool.fetchval = AsyncMock(return_value=2)
    pool.fetch = AsyncMock(
        return_value=[
            {"telefone": "5511111111111"},
            {"telefone": "5511222222222"},
        ]
    )

    monkeypatch.setattr(
        servico,
        "obter_identificadores_postgres",
        lambda: type("P", (), {"qual": lambda self, b: f"public.{b}"})(),
    )
    marcar = AsyncMock(side_effect=[True, False])
    monkeypatch.setattr(servico.engajamento_compradores_repo, "marcar_convertido_por_telefone", marcar)

    out = asyncio.run(servico.executar_sincronizar_conversoes_compradores(pool))
    assert out.avaliados == 2
    assert out.convertidos == 1
    assert marcar.await_count == 2
    sql = pool.fetch.await_args.args[0]
    assert "usuario_comprador" in sql
    assert "n_acessos" in sql

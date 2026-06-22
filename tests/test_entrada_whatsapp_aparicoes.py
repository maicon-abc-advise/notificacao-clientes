"""Testes da regra de aparições mínimas na entrada da fila WhatsApp."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.whatsapp.servicos.entrada_whatsapp_apos_falha_email import (
    _bloquear_poucas_aparicoes_primeira_entrada,
    _contar_aparicoes,
    entrada_whatsapp_apos_falha_email,
)


def _cfg(*, min_buscas: int = 5) -> MagicMock:
    cfg = MagicMock()
    cfg.routine_min_buscas = min_buscas
    return cfg


def test_contar_aparicoes_total() -> None:
    asyncio.run(_test_contar_aparicoes_total())


async def _test_contar_aparicoes_total() -> None:
    pool = AsyncMock()
    pool.fetchval = AsyncMock(return_value=7)
    n = await _contar_aparicoes(pool, "12345678")
    assert n == 7
    sql = pool.fetchval.await_args.args[0]
    assert "FROM" in sql and "aparicoes" in sql
    assert "created_at" not in sql


def test_bloquear_primeira_entrada_com_poucas_aparicoes() -> None:
    asyncio.run(_test_bloquear_primeira_entrada_com_poucas_aparicoes())


async def _test_bloquear_primeira_entrada_com_poucas_aparicoes() -> None:
    pool = AsyncMock()
    with patch(
        "app.whatsapp.servicos.entrada_whatsapp_apos_falha_email._contar_aparicoes",
        AsyncMock(return_value=3),
    ):
        out = await _bloquear_poucas_aparicoes_primeira_entrada(
            pool,
            _cfg(),
            cnpj_basico="12345678",
            origem="bounce_email",
            ultimo=None,
        )
    assert out is not None
    assert out["retorno"] == "whatsapp_ignorado_poucas_buscas"
    assert out["aparicoes"] == 3
    assert out["minimo"] == 5


def test_isenta_proximo_telefone_invalido() -> None:
    asyncio.run(_test_isenta_proximo_telefone_invalido())


async def _test_isenta_proximo_telefone_invalido() -> None:
    pool = AsyncMock()
    out = await _bloquear_poucas_aparicoes_primeira_entrada(
        pool,
        _cfg(),
        cnpj_basico="12345678",
        origem="proximo_telefone_invalido",
        ultimo=None,
    )
    assert out is None


def test_entrada_bounce_bloqueada_sem_aparicoes_suficientes() -> None:
    asyncio.run(_test_entrada_bounce_bloqueada_sem_aparicoes_suficientes())


async def _test_entrada_bounce_bloqueada_sem_aparicoes_suficientes() -> None:
    pool = AsyncMock()
    cfg = _cfg()

    with (
        patch(
            "app.whatsapp.servicos.entrada_whatsapp_apos_falha_email.repo.buscar_por_cnpj_telefone",
            AsyncMock(return_value=None),
        ),
        patch(
            "app.whatsapp.servicos.entrada_whatsapp_apos_falha_email.repo.buscar_ultimo_por_cnpj",
            AsyncMock(return_value=None),
        ),
        patch(
            "app.whatsapp.servicos.entrada_whatsapp_apos_falha_email._contar_aparicoes",
            AsyncMock(return_value=2),
        ),
    ):
        out = await entrada_whatsapp_apos_falha_email(
            pool,
            cfg,
            cnpj_basico="12345678",
            fornecedor_id=None,
            origem="bounce_email",
            telefone="5511999999999",
        )

    assert out["retorno"] == "whatsapp_ignorado_poucas_buscas"
    assert out["aparicoes"] == 2


def test_entrada_sweep_insere_com_aparicoes_suficientes() -> None:
    asyncio.run(_test_entrada_sweep_insere_com_aparicoes_suficientes())


async def _test_entrada_sweep_insere_com_aparicoes_suficientes() -> None:
    pool = AsyncMock()
    cfg = _cfg()
    row = {"id": 99, "numero_telefone": "5511999999999"}

    with (
        patch(
            "app.whatsapp.servicos.entrada_whatsapp_apos_falha_email.repo.buscar_por_cnpj_telefone",
            AsyncMock(return_value=None),
        ),
        patch(
            "app.whatsapp.servicos.entrada_whatsapp_apos_falha_email.repo.buscar_ultimo_por_cnpj",
            AsyncMock(return_value=None),
        ),
        patch(
            "app.whatsapp.servicos.entrada_whatsapp_apos_falha_email._contar_aparicoes",
            AsyncMock(return_value=6),
        ),
        patch(
            "app.whatsapp.servicos.entrada_whatsapp_apos_falha_email.repo.inserir_se_ausente",
            AsyncMock(return_value=(row, True)),
        ),
        patch(
            "app.whatsapp.servicos.entrada_whatsapp_apos_falha_email.tocar_engajamento_whatsapp",
            AsyncMock(),
        ),
    ):
        out = await entrada_whatsapp_apos_falha_email(
            pool,
            cfg,
            cnpj_basico="12345678",
            fornecedor_id=None,
            origem="sweep_emails_esperando_confirmacao",
            telefone="5511999999999",
        )

    assert out["retorno"] == "whatsapp_inserido"
    assert out["id"] == "99"


def test_reentrada_apos_falha_usa_aparicoes_desde_updated_at() -> None:
    asyncio.run(_test_reentrada_apos_falha_usa_aparicoes_desde_updated_at())


async def _test_reentrada_apos_falha_usa_aparicoes_desde_updated_at() -> None:
    pool = AsyncMock()
    cfg = _cfg()
    updated = datetime(2025, 1, 1, tzinfo=UTC)
    existente = {
        "id": 1,
        "status": "concluido_falha",
        "updated_at": updated,
        "numero_telefone": "5511999999999",
    }

    contar = AsyncMock(return_value=4)

    with (
        patch(
            "app.whatsapp.servicos.entrada_whatsapp_apos_falha_email.repo.buscar_por_cnpj_telefone",
            AsyncMock(return_value=existente),
        ),
        patch(
            "app.whatsapp.servicos.entrada_whatsapp_apos_falha_email._contar_aparicoes",
            contar,
        ),
        patch(
            "app.whatsapp.servicos.entrada_whatsapp_apos_falha_email._fornecedor_cadastrou",
            AsyncMock(return_value=False),
        ),
    ):
        out = await entrada_whatsapp_apos_falha_email(
            pool,
            cfg,
            cnpj_basico="12345678",
            fornecedor_id=None,
            origem="bounce_email",
            telefone="5511999999999",
        )

    assert out["retorno"] == "whatsapp_ignorado_falha"
    contar.assert_awaited_once_with(pool, "12345678", desde=updated)

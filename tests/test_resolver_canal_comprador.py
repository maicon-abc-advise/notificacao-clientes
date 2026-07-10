"""Testes do resolver de canal comprador com variáveis."""

from __future__ import annotations

import pytest

from app.config.variaveis_sistema import servico
from app.orquestracao.servicos.comprador_busca_constantes import CanalCompradorBusca
from app.orquestracao.servicos.resolver_canal_comprador_busca import (
    _obter_distribuicao_canais_comprador,
    resolver_canal_comprador_busca,
)


@pytest.fixture(autouse=True)
def _limpar_cache() -> None:
    servico.invalidar_cache_variaveis()
    yield
    servico.invalidar_cache_variaveis()


def test_resolver_canal_explicito() -> None:
    assert resolver_canal_comprador_busca(CanalCompradorBusca.SMS) == CanalCompradorBusca.SMS


def test_distribuicao_lê_cache_banco() -> None:
    servico._cache_banco = {
        "comprador_pct_sms": "70",
        "comprador_pct_rcs": "20",
        "comprador_pct_whatsapp": "10",
    }
    dist = _obter_distribuicao_canais_comprador()
    assert dist[CanalCompradorBusca.SMS] == 70.0
    assert dist[CanalCompradorBusca.RCS] == 20.0
    assert dist[CanalCompradorBusca.WHATSAPP] == 10.0

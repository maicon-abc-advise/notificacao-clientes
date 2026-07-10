"""Testes de variáveis de sistema (cache, fallback .env, validação)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.config.variaveis_sistema import servico
from app.config.variaveis_sistema.modelo import TipoVariavelSistema


@pytest.fixture(autouse=True)
def _limpar_cache_variaveis() -> None:
    servico.invalidar_cache_variaveis()
    yield
    servico.invalidar_cache_variaveis()


def test_obter_valor_fallback_env_sem_cache() -> None:
    assert servico.obter_int("sweep_esperando_confirmacao_dias") >= 1
    assert servico.obter_float("comprador_pct_sms") == 100.0


def test_obter_valor_prioriza_banco() -> None:
    servico._cache_banco = {"comprador_pct_sms": "80", "comprador_pct_rcs": "10", "comprador_pct_whatsapp": "10"}
    assert servico.obter_float("comprador_pct_sms") == 80.0
    assert servico.obter_str("comprador_pct_rcs") == "10"


def test_validar_pct_comprador_rejeita_soma_errada() -> None:
    cache = {"comprador_pct_sms": "95", "comprador_pct_rcs": "5", "comprador_pct_whatsapp": "5"}
    with pytest.raises(HTTPException) as exc:
        servico._validar_pct_comprador(cache)
    assert exc.value.status_code == 400


def test_validar_valor_bool() -> None:
    assert servico._validar_valor_para_tipo("sim", TipoVariavelSistema.BOOL) == "true"
    assert servico._validar_valor_para_tipo("false", TipoVariavelSistema.BOOL) == "false"


def test_validar_valor_percent_fora_faixa() -> None:
    with pytest.raises(ValueError):
        servico._validar_valor_para_tipo("150", TipoVariavelSistema.PERCENT)

"""GET /v1/clique/{token} — JSON e CORS."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.clique.token_clique import gerar_token_clique
from app.config.config import obter_configuracao
from app.main import app


@pytest.fixture(autouse=True)
def _limpar_cache() -> None:
    obter_configuracao.cache_clear()
    yield
    obter_configuracao.cache_clear()


def test_clique_token_invalido_retorna_404() -> None:
    with TestClient(app) as client:
        res = client.get("/v1/clique/token-invalido")
    assert res.status_code == 404


def test_clique_token_valido_sem_envio_retorna_404() -> None:
    secret = obter_configuracao().link_clique_secret
    token = gerar_token_clique("id-que-nao-existe-no-banco", secret)
    pool = MagicMock()
    with (
        patch("app.clique.api.rotas_clique.obter_pool", new_callable=AsyncMock, return_value=pool),
        patch(
            "app.clique.api.rotas_clique.processar_clique_api",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        with TestClient(app) as client:
            res = client.get(f"/v1/clique/{token}")
    assert res.status_code == 404


def test_clique_json_ok() -> None:
    secret = obter_configuracao().link_clique_secret
    token = gerar_token_clique("ext-teste-json", secret)
    pool = MagicMock()
    with (
        patch("app.clique.api.rotas_clique.obter_pool", new_callable=AsyncMock, return_value=pool),
        patch(
            "app.clique.api.rotas_clique.processar_clique_api",
            new_callable=AsyncMock,
            return_value={"uf": "SP", "segmento": "papel", "nome_empresa": "ACME"},
        ),
    ):
        with TestClient(app) as client:
            res = client.get(f"/v1/clique/{token}")
    assert res.status_code == 200
    assert res.json() == {"uf": "SP", "segmento": "papel", "nome_empresa": "ACME"}


def test_cors_origens_incluem_buscafornecedor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "https://buscafornecedor.com.br,https://www.buscafornecedor.com.br",
    )
    obter_configuracao.cache_clear()
    origens = obter_configuracao().listar_origens_cors()
    assert "https://buscafornecedor.com.br" in origens
    assert "https://www.buscafornecedor.com.br" in origens


def test_obter_dados_nome_empresa_padrao() -> None:
    from app.clique.servicos.registrar_clique import _nome_empresa_resposta

    assert _nome_empresa_resposta("") == "Sua empresa"
    assert _nome_empresa_resposta("  ACME  ") == "ACME"

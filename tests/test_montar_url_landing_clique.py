import pytest

from app.clique.servicos.registrar_clique import montar_url_landing_info_consulta
from app.config.config import obter_configuracao


@pytest.fixture(autouse=True)
def _limpar_cache() -> None:
    obter_configuracao.cache_clear()
    yield
    obter_configuracao.cache_clear()


def test_landing_query_params(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "URL_LANDING_INFO_CONSULTA",
        "https://buscafornecedor.com.br/info-consulta",
    )
    obter_configuracao.cache_clear()
    cfg = obter_configuracao()
    url = montar_url_landing_info_consulta(
        cfg,
        segmento="Equipamentos industriais",
        uf="SP",
        nome_empresa="",
    )
    assert url.startswith("https://buscafornecedor.com.br/info-consulta?")
    assert "nome_empresa=Sua+empresa" in url or "nome_empresa=Sua%20empresa" in url
    assert "uf=SP" in url
    assert "segmento=" in url


def test_landing_com_nome_fantasia(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("URL_LANDING_INFO_CONSULTA", "https://exemplo.com/info-consulta")
    obter_configuracao.cache_clear()
    cfg = obter_configuracao()
    url = montar_url_landing_info_consulta(
        cfg,
        segmento="papel",
        uf="GO",
        nome_empresa="Metal Sul",
    )
    assert "nome_empresa=Metal" in url

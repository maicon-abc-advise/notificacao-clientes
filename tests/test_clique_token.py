import pytest

from app.clique.token_clique import extrair_id_externo_do_token, gerar_token_clique
from app.config.config import obter_configuracao


@pytest.fixture(autouse=True)
def _limpar_cache() -> None:
    obter_configuracao.cache_clear()
    yield
    obter_configuracao.cache_clear()


def test_token_roundtrip() -> None:
    secret = "test-secret-clique"
    id_externo = "550e8400-e29b-41d4-a716-446655440000"
    token = gerar_token_clique(id_externo, secret)
    assert extrair_id_externo_do_token(token, secret) == id_externo


def test_token_invalido() -> None:
    assert extrair_id_externo_do_token("invalido", "secret") is None
    assert extrair_id_externo_do_token("", "secret") is None

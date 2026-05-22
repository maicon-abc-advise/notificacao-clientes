import pytest

from app.clique.token_clique import (
    TAMANHO_ID_EXTERNO,
    TAMANHO_TOKEN_URL,
    cifrar_id_para_url,
    decifrar_url_para_id,
    gerar_id_externo,
)


def test_gerar_id_externo_tamanho_e_alfabeto() -> None:
    id_externo = gerar_id_externo()
    assert len(id_externo) == TAMANHO_ID_EXTERNO
    assert id_externo.isalnum()


def test_cifra_decifra_roundtrip() -> None:
    secret = "test-secret-clique"
    id_externo = gerar_id_externo()
    token = cifrar_id_para_url(id_externo, secret)
    assert len(token) == TAMANHO_TOKEN_URL
    assert decifrar_url_para_id(token, secret) == id_externo


def test_token_invalido() -> None:
    secret = "test-secret-clique"
    assert decifrar_url_para_id("curto", secret) is None
    assert decifrar_url_para_id("x" * 20, secret) is None
    assert decifrar_url_para_id("", secret) is None

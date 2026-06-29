import asyncio

import pytest

from app.experimentos.growthbook_servico import resolver_variante_email_busca
from app.experimentos.variante_email import normalizar_variante
from app.templates.modelo import CodigoTipoTemplate


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("simples", "simples"),
        ("elaborado", "elaborado"),
        ("ELABORADO", "elaborado"),
        ("", "simples"),
        ("outro", "simples"),
    ],
)
def test_normalizar_variante(entrada: str, esperado: str) -> None:
    assert normalizar_variante(entrada) == esperado


def test_resolver_desligado_retorna_simples_sem_experimento(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROWTHBOOK_ENABLED", "false")
    monkeypatch.setenv("DASHBOARD_LOGIN", "u")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "p")

    variante, exp = asyncio.run(
        resolver_variante_email_busca(
            "12345678",
            tipo_template=CodigoTipoTemplate.APARECEU_BUSCA,
        )
    )
    assert variante == "simples"
    assert exp is None


def test_resolver_ignora_tipo_nao_busca(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROWTHBOOK_ENABLED", "true")
    monkeypatch.setenv("GROWTHBOOK_CLIENT_KEY", "sdk-test")
    monkeypatch.setenv("DASHBOARD_LOGIN", "u")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "p")

    variante, exp = asyncio.run(
        resolver_variante_email_busca(
            "12345678",
            tipo_template=CodigoTipoTemplate.CREDITOS_NO_FIM,
        )
    )
    assert variante == "simples"
    assert exp is None

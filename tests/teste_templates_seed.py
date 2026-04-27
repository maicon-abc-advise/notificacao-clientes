"""Testes sem Postgres: contrato dos dados de seed."""

from app.templates.dados_seed import linhas_seed
from app.templates.modelo import CodigoTipoTemplate


def test_seed_quatro_linhas() -> None:
    linhas = linhas_seed()
    assert len(linhas) == 4
    tipos = {t[1] for t in linhas}
    assert tipos == {e.value for e in CodigoTipoTemplate}


def test_consultado_sem_email_sem_corpo_html() -> None:
    for id_, tipo, email, sms in linhas_seed():
        if tipo == CodigoTipoTemplate.CONSULTADO_SEM_EMAIL.value:
            assert email is None
            assert "{{ url_plataforma }}" in sms
            return
    raise AssertionError("tipo CONSULTADO_SEM_EMAIL ausente")

import pytest

from app.templates.assunto_email import assunto_email_para_tipo
from app.templates.modelo import CodigoTipoTemplate


def test_assunto_apareceu_busca() -> None:
    assert "busca" in assunto_email_para_tipo(CodigoTipoTemplate.APARECEU_BUSCA).lower()


def test_assunto_apareceu_busca_sem_registro() -> None:
    a = assunto_email_para_tipo(CodigoTipoTemplate.APARECEU_BUSCA_SEM_REGISTRO)
    assert "busca" in a.lower()


def test_consultado_sem_email_sem_assunto_definido() -> None:
    with pytest.raises(ValueError, match="CONSULTADO_SEM_EMAIL"):
        assunto_email_para_tipo(CodigoTipoTemplate.CONSULTADO_SEM_EMAIL)

from app.reenvio.servicos.classificar_cause_email import (
    ResultadoClassificacaoEmail,
    classificar_falha_email,
    classificar_falha_sms_numero,
)


def test_hard_bounce_por_550() -> None:
    assert (
        classificar_falha_email(cause="550 5.1.1 user unknown", description=None)
        == ResultadoClassificacaoEmail.HARD_BOUNCE
    )


def test_mailbox_full() -> None:
    assert (
        classificar_falha_email(cause="452 mailbox full", description=None)
        == ResultadoClassificacaoEmail.MAILBOX_FULL
    )


def test_unknown_vazio() -> None:
    assert classificar_falha_email(cause=None, description=None) == ResultadoClassificacaoEmail.UNKNOWN


def test_sms_numero_invalido() -> None:
    assert classificar_falha_sms_numero(cause="invalid phone number", description=None) is True

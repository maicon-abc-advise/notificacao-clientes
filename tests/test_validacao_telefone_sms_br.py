"""Validação móvel BR para SMS (contingência telefones)."""

from app.reenvio.servicos.validacao_telefone_sms_br import (
    MOTIVO_FALHA_SMS_TELEFONE_INVALIDO,
    garantir_prefixo_55_digitos,
    normalizar_telefone_movel_br_para_sms,
    validar_telefone_para_sms_br,
)


def test_movel_11_digitos_nacionais_ok() -> None:
    assert normalizar_telefone_movel_br_para_sms("5511999887766") == "5511999887766"
    assert validar_telefone_para_sms_br("(11) 99988-7766")


def test_movel_sem_55_ok() -> None:
    assert normalizar_telefone_movel_br_para_sms("11999887766") == "5511999887766"


def test_legado_10_digitos_insere_9() -> None:
    """DDD + 8 dígitos começando em 6–8 (móvel sem 9 inicial após DDD)."""
    assert normalizar_telefone_movel_br_para_sms("21987654321") == "5521987654321"


def test_dez_digitos_nacionais_com_9_apos_ddd_sem_inserir_outro_nove() -> None:
    """DDD + 9 + oito dígitos (10 nacionais) — não duplicar o 9 (ex.: links wa.me)."""
    assert normalizar_telefone_movel_br_para_sms("553499112233") == "553499112233"


def test_fixo_rejeitado() -> None:
    assert normalizar_telefone_movel_br_para_sms("553532314000") is None
    assert not validar_telefone_para_sms_br("(35) 3231-4000")


def test_servico_rejeitado() -> None:
    assert normalizar_telefone_movel_br_para_sms("558007700077") is None


def test_tamanho_e164_invalido() -> None:
    assert normalizar_telefone_movel_br_para_sms("551199988776612345") is None


def test_garantir_55_idempotente() -> None:
    assert garantir_prefixo_55_digitos("5511999999999") == "5511999999999"
    assert garantir_prefixo_55_digitos("11999999999") == "5511999999999"


def test_motivo_constante() -> None:
    assert "INVÁLIDO" in MOTIVO_FALHA_SMS_TELEFONE_INVALIDO

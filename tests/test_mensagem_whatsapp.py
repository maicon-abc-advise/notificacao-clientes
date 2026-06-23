"""Testes de templates e seleção de mensagem WhatsApp."""

from app.whatsapp.servicos.mensagem_inicial import (
    escolher_mensagem_contato,
    montar_mensagem_followup_cadastro,
    montar_mensagem_inicial,
    row_tem_sucesso_sem_cadastro,
)


def test_mensagem_inicial() -> None:
    msg = montar_mensagem_inicial()
    assert "BuscaFornecedor" in msg
    assert "cotação" in msg
    assert "segmento" not in msg.lower()


def test_mensagem_followup_cadastro() -> None:
    msg = montar_mensagem_followup_cadastro("Metalurgia")
    assert "conseguiu fazer o cadastro" in msg
    assert "Metalurgia" in msg
    assert "buscafornecedor.com.br" in msg


def test_escolher_mensagem_primeiro_contato() -> None:
    row = {"etapa1": None, "etapa2": None, "etapa3": None}
    msg = escolher_mensagem_contato(row, "Serviços")
    assert msg == montar_mensagem_inicial()


def test_escolher_mensagem_followup_apos_sucesso_sem_cadastro() -> None:
    row = {"etapa1": "sucesso_sem_cadastro", "etapa2": None, "etapa3": None}
    assert row_tem_sucesso_sem_cadastro(row)
    msg = escolher_mensagem_contato(row, "Serviços")
    assert msg == montar_mensagem_followup_cadastro("Serviços")


def test_escolher_mensagem_followup_na_etapa_2_ou_3() -> None:
    row = {"etapa1": "ignorado", "etapa2": "sucesso_sem_cadastro", "etapa3": None}
    msg = escolher_mensagem_contato(row, None)
    assert "conseguiu fazer o cadastro" in msg

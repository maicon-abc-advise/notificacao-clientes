"""Validação do corpo de recebe-consulta: e-mail e telefone opcionais e normalização de vazio."""

from uuid import uuid4

from app.orquestracao.api.dto.recebe_consulta_dto import RecebeConsultaCorpo


def test_recebe_consulta_sem_email_nem_telefone() -> None:
    m = RecebeConsultaCorpo(
        id_consulta=uuid4(),
        cnpj_basico="12345678",
        cnpj_ordem="0001",
        cnpj_dv="00",
    )
    assert m.email_fornecedor is None
    assert m.telefone_fornecedor is None


def test_recebe_consulta_email_e_telefone_branco_vao_para_none() -> None:
    m = RecebeConsultaCorpo(
        id_consulta=uuid4(),
        cnpj_basico="12345678",
        cnpj_ordem="0001",
        cnpj_dv="00",
        email_fornecedor="   ",
        telefone_fornecedor="",
    )
    assert m.email_fornecedor is None
    assert m.telefone_fornecedor is None


def test_recebe_consulta_email_valido() -> None:
    m = RecebeConsultaCorpo(
        id_consulta=uuid4(),
        cnpj_basico="12345678",
        cnpj_ordem="0001",
        cnpj_dv="00",
        email_fornecedor="a@b.co",
    )
    assert m.email_fornecedor == "a@b.co"


def test_recebe_consulta_uf_e_segmento_opcionais() -> None:
    m = RecebeConsultaCorpo(
        id_consulta=uuid4(),
        cnpj_basico="12345678",
        cnpj_ordem="0001",
        cnpj_dv="00",
        uf="  MG ",
        segmento="  papel  ",
    )
    assert m.uf == "MG"
    assert m.segmento == "papel"

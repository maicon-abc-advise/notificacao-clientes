from uuid import uuid4

from app.orquestracao.api.dto.recebe_consulta_dto import RecebeConsultaCorpo
from app.orquestracao.servicos.auxiliares.montar_pedido_mensagem import (
    montar_pedido_email_apareceu_busca,
    montar_pedido_sms_consultado_sem_email,
)
from app.templates.modelo import CodigoTipoTemplate


def _corpo() -> RecebeConsultaCorpo:
    return RecebeConsultaCorpo(
        id_consulta=uuid4(),
        cnpj_basico="12345678",
        cnpj_ordem="0001",
        cnpj_dv="00",
        nome_fantasia="ACME",
    )


def test_pedido_email_apareceu_busca_contexto_minimo_logado() -> None:
    c = _corpo()
    p = montar_pedido_email_apareceu_busca(
        c,
        destinatario="a@b.co",
        fornecedor_id=None,
        cnpj_basico=c.cnpj_basico,
        id_externo="ext-1",
        tipo_template=CodigoTipoTemplate.APARECEU_BUSCA,
        uf="MG",
        segmento="alimentícios",
    )
    assert p.contexto == {
        "saudacao_nome": "ACME",
        "uf": "MG",
        "segmento": "alimentícios",
        "link_area_conta": "https://buscafornecedor.com.br/conta",
        "url_plataforma": "https://buscafornecedor.com.br",
    }


def test_pedido_email_sem_registro_contexto_minimo() -> None:
    c = _corpo()
    p = montar_pedido_email_apareceu_busca(
        c,
        destinatario="a@b.co",
        fornecedor_id=None,
        cnpj_basico=c.cnpj_basico,
        id_externo="ext-1",
        tipo_template=CodigoTipoTemplate.APARECEU_BUSCA_SEM_REGISTRO,
        uf="MG",
        segmento="alimentícios",
    )
    assert p.contexto == {
        "saudacao_nome": "ACME",
        "uf": "MG",
        "segmento": "alimentícios",
        "link_cadastro": "https://buscafornecedor.com.br/cadastro",
        "url_plataforma": "https://buscafornecedor.com.br",
    }


def test_pedido_sms_busca_contexto_minimo() -> None:
    c = _corpo()
    p = montar_pedido_sms_consultado_sem_email(
        c,
        destinatario="5511999999999",
        fornecedor_id=None,
        cnpj_basico=c.cnpj_basico,
        id_externo="ext-2",
        tipo_template=CodigoTipoTemplate.CONSULTADO_SEM_EMAIL,
        uf="sua região",
        segmento="seu segmento",
    )
    assert p.contexto == {
        "uf": "sua região",
        "segmento": "seu segmento",
        "url_plataforma": "https://buscafornecedor.com.br",
    }

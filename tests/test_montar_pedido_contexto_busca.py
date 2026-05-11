from uuid import uuid4

import pytest

from app.config.config import obter_configuracao
from app.orquestracao.api.dto.recebe_consulta_dto import RecebeConsultaCorpo
from app.orquestracao.servicos.auxiliares.montar_pedido_mensagem import (
    montar_pedido_email_apareceu_busca,
    montar_pedido_email_creditos_no_fim,
    montar_pedido_sms_consultado_sem_email,
    montar_pedido_sms_creditos_no_fim,
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
        "url_plataforma": "https://buscafornecedor.com.br",
        "url_login": "https://buscafornecedor.com.br/login",
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
        "url_plataforma": "https://buscafornecedor.com.br",
        "url_login": "https://buscafornecedor.com.br/login",
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
        "url_login": "https://buscafornecedor.com.br/login",
    }


@pytest.fixture(autouse=True)
def _limpar_cache_config() -> None:
    obter_configuracao.cache_clear()
    yield
    obter_configuracao.cache_clear()


def test_contexto_busca_usa_urls_distintas_por_canal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("URL_PLATAFORMA_EMAIL", "https://email.exemplo.com")
    monkeypatch.setenv("URL_LOGIN_EMAIL", "https://email.exemplo.com/login")
    monkeypatch.setenv("URL_PLATAFORMA_SMS", "https://sms.exemplo.com")
    monkeypatch.setenv("URL_LOGIN_SMS", "https://sms.exemplo.com/login")
    obter_configuracao.cache_clear()

    c = _corpo()
    pedido_email = montar_pedido_email_apareceu_busca(
        c,
        destinatario="a@b.co",
        fornecedor_id=None,
        cnpj_basico=c.cnpj_basico,
        id_externo="ext-email",
        tipo_template=CodigoTipoTemplate.APARECEU_BUSCA,
        uf="MG",
        segmento="alimentícios",
    )
    pedido_sms = montar_pedido_sms_consultado_sem_email(
        c,
        destinatario="5511999999999",
        fornecedor_id=None,
        cnpj_basico=c.cnpj_basico,
        id_externo="ext-sms",
        tipo_template=CodigoTipoTemplate.CONSULTADO_SEM_EMAIL,
        uf="MG",
        segmento="alimentícios",
    )

    assert pedido_email.contexto["url_plataforma"] == "https://email.exemplo.com"
    assert pedido_email.contexto["url_login"] == "https://email.exemplo.com/login"
    assert pedido_sms.contexto["url_plataforma"] == "https://sms.exemplo.com"
    assert pedido_sms.contexto["url_login"] == "https://sms.exemplo.com/login"


def test_contexto_creditos_usa_links_distintos_por_canal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("URL_PLATAFORMA_EMAIL", "https://painel.exemplo.com")
    monkeypatch.setenv("URL_PLATAFORMA_SMS", "https://app.exemplo.com")
    monkeypatch.setenv("URL_LOGIN_EMAIL", "https://painel.exemplo.com/login")
    monkeypatch.setenv("URL_LOGIN_SMS", "https://app.exemplo.com/login")
    obter_configuracao.cache_clear()

    pedido_email = montar_pedido_email_creditos_no_fim(
        destinatario="a@b.co",
        fornecedor_id=uuid4(),
        cnpj_basico="12345678",
        id_externo="cred-email",
        nome_fantasia="ACME",
        url_login="https://painel.exemplo.com/login",
    )
    pedido_sms = montar_pedido_sms_creditos_no_fim(
        destinatario="5511999999999",
        fornecedor_id=uuid4(),
        cnpj_basico="12345678",
        id_externo="cred-sms",
        nome_fantasia="ACME",
        url_login="https://app.exemplo.com/login",
    )

    assert pedido_email.contexto == {
        "saudacao_nome": "ACME",
        "url_plataforma": "https://painel.exemplo.com",
        "url_login": "https://painel.exemplo.com/login",
    }
    assert pedido_sms.contexto == {
        "url_plataforma": "https://app.exemplo.com",
        "url_login": "https://app.exemplo.com/login",
    }

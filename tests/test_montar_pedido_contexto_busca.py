from uuid import uuid4

import pytest

from app.clique.token_clique import (
    TAMANHO_TOKEN_URL,
    decifrar_url_para_id,
    gerar_id_externo,
)
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
    id_externo = gerar_id_externo()
    p = montar_pedido_email_apareceu_busca(
        c,
        destinatario="a@b.co",
        fornecedor_id=None,
        cnpj_basico=c.cnpj_basico,
        id_externo=id_externo,
        tipo_template=CodigoTipoTemplate.APARECEU_BUSCA,
        uf="MG",
        segmento="alimentícios",
    )
    cfg = obter_configuracao()
    assert p.contexto["saudacao_nome"] == "ACME"
    assert p.contexto["uf"] == "MG"
    assert p.contexto["segmento"] == "alimentícios"
    assert p.contexto["url_plataforma"] == "https://buscafornecedor.com.br"
    assert "url_clique" not in p.contexto
    url_login = p.contexto["url_login"]
    assert url_login.startswith(f"{cfg.url_base_clique}/")
    token = url_login.rsplit("/", 1)[-1]
    assert len(token) == TAMANHO_TOKEN_URL
    assert decifrar_url_para_id(token, cfg.link_clique_secret) == id_externo


def test_pedido_email_sem_registro_contexto_minimo() -> None:
    c = _corpo()
    p = montar_pedido_email_apareceu_busca(
        c,
        destinatario="a@b.co",
        fornecedor_id=None,
        cnpj_basico=c.cnpj_basico,
        id_externo=gerar_id_externo(),
        tipo_template=CodigoTipoTemplate.APARECEU_BUSCA_SEM_REGISTRO,
        uf="MG",
        segmento="alimentícios",
    )
    assert "url_clique" not in p.contexto
    assert p.contexto["saudacao_nome"] == "ACME"
    assert p.contexto["url_login"].startswith(obter_configuracao().url_base_clique)


def test_pedido_sms_busca_contexto_minimo() -> None:
    c = _corpo()
    id_externo = gerar_id_externo()
    p = montar_pedido_sms_consultado_sem_email(
        c,
        destinatario="5511999999999",
        fornecedor_id=None,
        cnpj_basico=c.cnpj_basico,
        id_externo=id_externo,
        tipo_template=CodigoTipoTemplate.CONSULTADO_SEM_EMAIL,
        uf="GO",
        segmento="papel",
    )
    cfg = obter_configuracao()
    assert p.contexto["uf"] == "GO"
    assert p.contexto["segmento"] == "papel"
    assert "url_clique" not in p.contexto
    token = p.contexto["url_login"].rsplit("/", 1)[-1]
    assert len(token) == TAMANHO_TOKEN_URL
    assert decifrar_url_para_id(token, cfg.link_clique_secret) == id_externo


def test_pedido_sms_uf_ou_segmento_longos_vao_vazio() -> None:
    c = _corpo()
    p = montar_pedido_sms_consultado_sem_email(
        c,
        destinatario="5511999999999",
        fornecedor_id=None,
        cnpj_basico=c.cnpj_basico,
        id_externo=gerar_id_externo(),
        tipo_template=CodigoTipoTemplate.CONSULTADO_SEM_EMAIL,
        uf="GO,SP,MS",
        segmento="123456789",
    )
    assert p.contexto["uf"] == ""
    assert p.contexto["segmento"] == ""


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
    monkeypatch.setenv("URL_BASE_CLIQUE", "https://buscafornecedor.com.br/c")
    obter_configuracao.cache_clear()

    c = _corpo()
    id_email = gerar_id_externo()
    id_sms = gerar_id_externo()
    pedido_email = montar_pedido_email_apareceu_busca(
        c,
        destinatario="a@b.co",
        fornecedor_id=None,
        cnpj_basico=c.cnpj_basico,
        id_externo=id_email,
        tipo_template=CodigoTipoTemplate.APARECEU_BUSCA,
        uf="MG",
        segmento="alimentícios",
    )
    pedido_sms = montar_pedido_sms_consultado_sem_email(
        c,
        destinatario="5511999999999",
        fornecedor_id=None,
        cnpj_basico=c.cnpj_basico,
        id_externo=id_sms,
        tipo_template=CodigoTipoTemplate.CONSULTADO_SEM_EMAIL,
        uf="MG",
        segmento="alimentícios",
    )

    assert pedido_email.contexto["url_plataforma"] == "https://email.exemplo.com"
    assert pedido_email.contexto["url_login"].startswith("https://buscafornecedor.com.br/c/")
    assert len(pedido_email.contexto["url_login"].rsplit("/", 1)[-1]) == TAMANHO_TOKEN_URL
    assert pedido_sms.contexto["url_plataforma"] == "https://sms.exemplo.com"
    assert pedido_sms.contexto["url_login"].startswith("https://buscafornecedor.com.br/c/")
    assert len(pedido_sms.contexto["url_login"].rsplit("/", 1)[-1]) == TAMANHO_TOKEN_URL


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
        id_externo=gerar_id_externo(),
        nome_fantasia="ACME",
        url_login="https://painel.exemplo.com/login",
    )
    pedido_sms = montar_pedido_sms_creditos_no_fim(
        destinatario="5511999999999",
        fornecedor_id=uuid4(),
        cnpj_basico="12345678",
        id_externo=gerar_id_externo(),
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

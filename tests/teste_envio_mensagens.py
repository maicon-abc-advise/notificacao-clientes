"""Envio: autenticação interna e porta (Zenvia mockada via httpx)."""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.externo.zenvia.adaptador_envio import AdaptadorEnvioZenvia
from app.api.externo.zenvia.parametros import obter_parametros_zenvia
from app.main import app
from app.api.dto.modelos import (
    CanalMensagem,
    PedidoEnvioEmail,
    PedidoEnvioSms,
    ResultadoEnvioMensagem,
)
from app.config.dependencias import obter_porta_envio_mensagem


def _cliente_mensagem_200() -> httpx.Client:
    def tratar(requisicao: httpx.Request) -> httpx.Response:
        p = requisicao.url.path
        if p.endswith("/v2/channels/email/messages") or p.endswith("channels/email/messages"):
            return httpx.Response(200, json={"id": "e1", "channel": "email", "from": "a", "to": "b"})
        if p.endswith("/v2/channels/sms/messages") or p.endswith("channels/sms/messages"):
            return httpx.Response(200, json={"id": "s1", "channel": "sms", "from": "a", "to": "b"})
        return httpx.Response(500, text="rota inesperada: " + p)

    tr = httpx.MockTransport(tratar)
    return httpx.Client(
        transport=tr,
        base_url="https://api.zenvia.com",
        headers={"X-API-TOKEN": "t"},
    )


def test_adaptador_email_e_sms_ok() -> None:
    obter_parametros_zenvia.cache_clear()
    pz = obter_parametros_zenvia()
    cli = _cliente_mensagem_200()
    a = AdaptadorEnvioZenvia(pz, cliente=cli)
    r1 = a.enviar_email(
        PedidoEnvioEmail(
            destinatario="x@y.com",
            assunto="hi",
            corpo_html="<p>o</p>",
            remetente="sender-mail",
        )
    )
    assert r1.id_provedor == "e1"
    r2 = a.enviar_sms(
        PedidoEnvioSms(
            destinatario="5511999999999",
            texto="hello",
            remetente="sms-account",
        )
    )
    assert r2.id_provedor == "s1"
    a.fechar()


def test_post_email_401() -> None:
    with TestClient(app) as client:
        r = client.post(
            "/v1/mensagens/email",
            json={"destinatario": "a@b.com", "assunto": "s", "corpo_html": "<p>x</p>"},
        )
    assert r.status_code == 401


def test_post_email_200_com_override() -> None:
    class FalsaPorta:
        def enviar_email(self, pedido: PedidoEnvioEmail) -> ResultadoEnvioMensagem:
            return ResultadoEnvioMensagem(
                id_provedor="fake-1", canal=CanalMensagem.EMAIL, resposta_parcial={}
            )

        def enviar_sms(self, pedido: PedidoEnvioSms) -> ResultadoEnvioMensagem:
            raise NotImplementedError

    app.dependency_overrides[obter_porta_envio_mensagem] = lambda: FalsaPorta()
    r = None
    try:
        with TestClient(app) as client:
            r = client.post(
                "/v1/mensagens/email",
                headers={"Authorization": "Bearer test-api-key-unit"},
                json={
                    "destinatario": "a@b.com",
                    "assunto": "s",
                    "corpo_html": "<p>ok</p>",
                },
            )
    finally:
        app.dependency_overrides.clear()
    assert r is not None

    assert r.status_code == 200
    assert r.json()["id_provedor"] == "fake-1"


def test_503_se_sem_token_conector_zenvia(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.externo.zenvia.parametros import obter_parametros_zenvia
    from app.config.config import obter_configuracao

    # String vazia: conector zenvia trata como inexistente; o .env local pode ainda preencher via pydantic
    monkeypatch.setenv("ZENVIA_API_TOKEN", "")
    obter_configuracao.cache_clear()
    obter_parametros_zenvia.cache_clear()
    with TestClient(app) as client:
        r = client.post(
            "/v1/mensagens/sms",
            headers={"X-Api-Key": "test-api-key-unit"},
            json={"destinatario": "5511987654321", "texto": "hi", "remetente": "snd"},
        )
    assert r.status_code == 503
    monkeypatch.setenv("ZENVIA_API_TOKEN", "test-zenvia-token-somente-para-testes")
    obter_configuracao.cache_clear()
    obter_parametros_zenvia.cache_clear()

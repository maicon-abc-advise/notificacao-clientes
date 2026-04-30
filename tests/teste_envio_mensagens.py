"""Envio: autenticação interna e porta (Zenvia mockada via httpx)."""

import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config.dependencias_templates import obter_porta_templates
from app.main import app
from app.mensageria.api.rotas import envio_mensagens
from app.mensageria.api.dto.modelos import (
    CanalMensagem,
    PedidoEmailProvedor,
    PedidoSmsProvedor,
    ResultadoEnvioMensagem,
)
from app.mensageria.api.externo.zenvia.adaptador_envio import AdaptadorEnvioZenvia
from app.mensageria.api.externo.zenvia.parametros import obter_parametros_zenvia
from app.config.dependencias import obter_porta_envio_mensagem
from app.templates.modelo import TemplateNotificacao


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
        PedidoEmailProvedor(
            destinatario="x@y.com",
            assunto="hi",
            corpo_html="<p>o</p>",
            remetente="sender-mail",
        )
    )
    assert r1.id_provedor == "e1"
    r2 = a.enviar_sms(
        PedidoSmsProvedor(
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
            json={
                "destinatario": "a@b.com",
                "tipo_template": "APARECEU_BUSCA",
                "contexto": {},
            },
        )
    assert r.status_code == 401


async def _templates_fixos() -> object:
    class _T:
        async def obter_por_tipo(self, codigo: str) -> TemplateNotificacao:
            return TemplateNotificacao(
                id="1",
                tipo=codigo,
                email="<p>ok</p>",
                sms="sms",
            )

        async def listar_todos(self) -> list[TemplateNotificacao]:
            return []

    return _T()


def test_post_email_404_quando_fornecedor_id_inexistente() -> None:
    async def _fake_dep() -> object:
        return await _templates_fixos()

    app.dependency_overrides[obter_porta_templates] = _fake_dep
    try:
        with TestClient(app) as client:
            r = client.post(
                "/v1/mensagens/email",
                headers={"Authorization": "Bearer test-api-key-unit"},
                json={
                    "destinatario": "a@b.com",
                    "tipo_template": "APARECEU_BUSCA",
                    "contexto": {},
                    "fornecedor_id": str(uuid.uuid4()),
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 404
    assert r.json()["detail"] == "fornecedor não encontrado"


def test_post_sms_404_quando_fornecedor_id_inexistente() -> None:
    async def _fake_dep() -> object:
        return await _templates_fixos()

    app.dependency_overrides[obter_porta_templates] = _fake_dep
    try:
        with TestClient(app) as client:
            r = client.post(
                "/v1/mensagens/sms",
                headers={"Authorization": "Bearer test-api-key-unit"},
                json={
                    "destinatario": "5511987654321",
                    "tipo_template": "APARECEU_BUSCA",
                    "contexto": {},
                    "fornecedor_id": str(uuid.uuid4()),
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 404
    assert r.json()["detail"] == "fornecedor não encontrado"


def test_post_email_200_com_override() -> None:
    class FalsaPorta:
        def enviar_email(self, pedido: PedidoEmailProvedor) -> ResultadoEnvioMensagem:
            return ResultadoEnvioMensagem(
                id_provedor="fake-1", canal=CanalMensagem.EMAIL, resposta_parcial={}
            )

        def enviar_sms(self, pedido: PedidoSmsProvedor) -> ResultadoEnvioMensagem:
            raise NotImplementedError

    async def _fake_dep() -> object:
        return await _templates_fixos()

    app.dependency_overrides[obter_porta_envio_mensagem] = lambda: FalsaPorta()
    app.dependency_overrides[obter_porta_templates] = _fake_dep
    r = None
    try:
        with TestClient(app) as client:
            r = client.post(
                "/v1/mensagens/email",
                headers={"Authorization": "Bearer test-api-key-unit"},
                json={
                    "destinatario": "a@b.com",
                    "tipo_template": "APARECEU_BUSCA",
                    "contexto": {},
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert r is not None
    assert r.status_code == 200
    assert r.json()["id_provedor"] == "fake-1"


def test_post_email_idempotente_nao_chama_provedor() -> None:
    class PortaNaoDeveChamar:
        def enviar_email(self, pedido: PedidoEmailProvedor) -> ResultadoEnvioMensagem:
            raise AssertionError("envio não deve repetir quando id_externo já existe")

        def enviar_sms(self, pedido: PedidoSmsProvedor) -> ResultadoEnvioMensagem:
            raise NotImplementedError

    class _PoolFake:
        async def fetchrow(self, *_a, **_kw):
            return {"id_mensagem_zenvia": "z-já-gravado"}

    async def _pool_dep():
        return _PoolFake()

    async def _fake_dep() -> object:
        return await _templates_fixos()

    app.dependency_overrides[obter_porta_envio_mensagem] = lambda: PortaNaoDeveChamar()
    app.dependency_overrides[obter_porta_templates] = _fake_dep
    app.dependency_overrides[envio_mensagens._pool_mensagens] = _pool_dep
    try:
        with TestClient(app) as client:
            r = client.post(
                "/v1/mensagens/email",
                headers={"Authorization": "Bearer test-api-key-unit"},
                json={
                    "destinatario": "a@b.com",
                    "tipo_template": "APARECEU_BUSCA",
                    "contexto": {},
                    "id_externo": "idem-1",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200
    body = r.json()
    assert body["id_provedor"] == "z-já-gravado"
    assert body["resposta_parcial"].get("idempotente") is True


def test_post_sms_idempotente_nao_chama_provedor() -> None:
    class PortaNaoDeveChamar:
        def enviar_email(self, pedido: PedidoEmailProvedor) -> ResultadoEnvioMensagem:
            raise NotImplementedError

        def enviar_sms(self, pedido: PedidoSmsProvedor) -> ResultadoEnvioMensagem:
            raise AssertionError("envio SMS não deve repetir quando id_externo já existe")

    class _PoolFake:
        async def fetchrow(self, *_a, **_kw):
            return {"id_mensagem_zenvia": "s-já-gravado"}

    async def _pool_dep():
        return _PoolFake()

    async def _fake_dep() -> object:
        return await _templates_fixos()

    app.dependency_overrides[obter_porta_envio_mensagem] = lambda: PortaNaoDeveChamar()
    app.dependency_overrides[obter_porta_templates] = _fake_dep
    app.dependency_overrides[envio_mensagens._pool_mensagens] = _pool_dep
    try:
        with TestClient(app) as client:
            r = client.post(
                "/v1/mensagens/sms",
                headers={"Authorization": "Bearer test-api-key-unit"},
                json={
                    "destinatario": "5511987654321",
                    "tipo_template": "APARECEU_BUSCA",
                    "contexto": {},
                    "id_externo": "idem-sms-1",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200
    body = r.json()
    assert body["id_provedor"] == "s-já-gravado"
    assert body["resposta_parcial"].get("idempotente") is True


def test_503_se_sem_token_conector_zenvia(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.mensageria.api.externo.zenvia.parametros import obter_parametros_zenvia
    from app.config.config import obter_configuracao

    async def _fake_dep() -> object:
        return await _templates_fixos()

    monkeypatch.setenv("ZENVIA_API_TOKEN", "")
    monkeypatch.setenv("ZENVIA_API_TOKEN_PROD", "")
    obter_configuracao.cache_clear()
    obter_parametros_zenvia.cache_clear()
    app.dependency_overrides[obter_porta_templates] = _fake_dep
    try:
        with TestClient(app) as client:
            r = client.post(
                "/v1/mensagens/sms",
                headers={"X-Api-Key": "test-api-key-unit"},
                json={
                    "destinatario": "5511987654321",
                    "tipo_template": "APARECEU_BUSCA",
                    "contexto": {"link_area_conta": "https://exemplo.com"},
                },
            )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 503
    monkeypatch.setenv("ZENVIA_API_TOKEN", "test-zenvia-token-somente-para-testes")
    obter_configuracao.cache_clear()
    obter_parametros_zenvia.cache_clear()

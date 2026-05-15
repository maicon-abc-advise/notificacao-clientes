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
from app.reenvio.servicos.validacao_telefone_sms_br import MOTIVO_FALHA_SMS_TELEFONE_INVALIDO


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


async def _pool_dep_fornecedor_404():
    return _PoolFornecedorInexistente()


def test_post_email_404_quando_fornecedor_id_inexistente() -> None:
    async def _fake_dep() -> object:
        return await _templates_fixos()

    app.dependency_overrides[obter_porta_templates] = _fake_dep
    app.dependency_overrides[envio_mensagens._pool_mensagens] = _pool_dep_fornecedor_404
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
    app.dependency_overrides[envio_mensagens._pool_mensagens] = _pool_dep_fornecedor_404
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


async def _validar_engajamento_email_sem_db(*_a, **_k) -> str:
    return "12345678"


async def _exigir_engajamento_sms_noop(*_a, **_k) -> None:
    return None


async def _tocar_engajamento_noop(*_a, **_k) -> None:
    return None


class _PoolSemPostgres:
    """Substitui o pool real quando o fluxo do teste não executa SQL."""

    async def fetchval(self, *_a, **_k):
        return None

    async def fetchrow(self, *_a, **_k):
        return None


class _PoolFornecedorInexistente:
    async def fetchval(self, sql: str, *_args):
        if "EXISTS" in sql:
            return False
        return None

    async def fetchrow(self, *_a, **_k):
        return None


async def _pool_dep_sem_postgres():
    return _PoolSemPostgres()


def test_post_email_200_com_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        envio_mensagens,
        "_validar_engajamento_antes_envio_email",
        _validar_engajamento_email_sem_db,
    )
    monkeypatch.setattr(envio_mensagens, "tocar_engajamento_email", _tocar_engajamento_noop)
    app.dependency_overrides[envio_mensagens._pool_mensagens] = _pool_dep_sem_postgres

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
                    "cnpj_basico": "12345678",
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


def test_post_sms_400_telefone_fixo_nao_chama_provedor_grava_falha(monkeypatch: pytest.MonkeyPatch) -> None:
    falhas: list[dict] = []

    async def _captura_falha(pool, **kw: object) -> None:
        falhas.append(kw)

    async def _noop(*_a, **_k) -> None:
        return None

    monkeypatch.setattr(envio_mensagens, "exigir_destinatario_no_engajamento_sms", _noop)
    monkeypatch.setattr(envio_mensagens, "tocar_engajamento_sms", _noop)
    monkeypatch.setattr(envio_mensagens, "inserir_ou_atualizar_falha_validacao_telefone_sms", _captura_falha)

    class PortaNaoChama:
        def enviar_sms(self, *_a, **_k) -> ResultadoEnvioMensagem:
            raise AssertionError("provedor não deve ser chamado")

    async def _fake_dep() -> object:
        return await _templates_fixos()

    app.dependency_overrides[obter_porta_envio_mensagem] = lambda: PortaNaoChama()
    app.dependency_overrides[obter_porta_templates] = _fake_dep
    app.dependency_overrides[envio_mensagens._pool_mensagens] = _pool_dep_sem_postgres
    try:
        with TestClient(app) as client:
            r = client.post(
                "/v1/mensagens/sms",
                headers={"Authorization": "Bearer test-api-key-unit"},
                json={
                    "destinatario": "551132321010",
                    "tipo_template": "APARECEU_BUSCA",
                    "contexto": {},
                    "cnpj_basico": "12345678",
                    "id_externo": "invalid-phone-1",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 400
    assert r.json()["detail"] == MOTIVO_FALHA_SMS_TELEFONE_INVALIDO
    assert len(falhas) == 1
    assert falhas[0]["motivo"] == MOTIVO_FALHA_SMS_TELEFONE_INVALIDO


def test_503_se_sem_token_conector_zenvia(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.mensageria.api.externo.zenvia.parametros import obter_parametros_zenvia
    from app.config.config import obter_configuracao

    monkeypatch.setattr(
        envio_mensagens,
        "exigir_destinatario_no_engajamento_sms",
        _exigir_engajamento_sms_noop,
    )

    async def _fake_dep() -> object:
        return await _templates_fixos()

    monkeypatch.setenv("USE_ZENVIA_MOCK", "false")
    monkeypatch.setenv("ZENVIA_API_TOKEN", "")
    monkeypatch.setenv("ZENVIA_API_TOKEN_PROD", "")
    obter_configuracao.cache_clear()
    obter_parametros_zenvia.cache_clear()
    app.dependency_overrides[obter_porta_templates] = _fake_dep
    app.dependency_overrides[envio_mensagens._pool_mensagens] = _pool_dep_sem_postgres
    try:
        with TestClient(app) as client:
            r = client.post(
                "/v1/mensagens/sms",
                headers={"X-Api-Key": "test-api-key-unit"},
                json={
                    "destinatario": "5511987654321",
                    "tipo_template": "APARECEU_BUSCA",
                    "contexto": {"url_login": "https://exemplo.com/login"},
                    "cnpj_basico": "12345678",
                },
            )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 503
    monkeypatch.setenv("USE_ZENVIA_MOCK", "true")
    monkeypatch.setenv("ZENVIA_API_TOKEN", "test-zenvia-token-somente-para-testes")
    obter_configuracao.cache_clear()
    obter_parametros_zenvia.cache_clear()

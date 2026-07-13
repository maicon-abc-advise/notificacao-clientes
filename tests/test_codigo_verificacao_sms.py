"""Testes do endpoint SMS código de verificação."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config.dependencias import obter_porta_envio_mensagem
from app.config.dependencias_templates import obter_porta_templates
from app.main import app
from app.orquestracao.api.dependencias import _pool
from app.orquestracao.api.dto.codigo_verificacao_dto import RespostaSmsCodigoVerificacao
from app.orquestracao.api.rotas import codigo_verificacao_rota
from app.orquestracao.servicos import enviar_sms_codigo_verificacao as servico
from app.templates.modelo import CodigoTipoTemplate, TemplateNotificacao


@pytest.fixture
def client_codigo_verificacao(monkeypatch: pytest.MonkeyPatch):
    async def _executar(*_a, **_k):
        return RespostaSmsCodigoVerificacao(
            id_externo="codigo-verificacao-x",
            id_provedor="zenvia-mock-1",
            status_ultimo="processando",
        )

    monkeypatch.setattr(
        codigo_verificacao_rota,
        "executar_envio_sms_codigo_verificacao",
        _executar,
    )

    async def _pool_fake():
        return AsyncMock()

    app.dependency_overrides[_pool] = _pool_fake
    app.dependency_overrides[obter_porta_envio_mensagem] = lambda: AsyncMock()

    async def _templates_fake():
        return AsyncMock()

    app.dependency_overrides[obter_porta_templates] = _templates_fake
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_post_codigo_verificacao_sms_401() -> None:
    with TestClient(app) as client:
        r = client.post(
            "/v1/interno/orquestracao/codigo-verificacao/sms",
            json={"telefone": "5511999999999", "codigo": "123456"},
        )
    assert r.status_code == 401


def test_post_codigo_verificacao_sms_200(client_codigo_verificacao: TestClient) -> None:
    r = client_codigo_verificacao.post(
        "/v1/interno/orquestracao/codigo-verificacao/sms",
        headers={"X-Api-Key": "test-api-key-unit"},
        json={"telefone": "5511999999999", "codigo": "123456"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["id_externo"] == "codigo-verificacao-x"
    assert body["id_provedor"] == "zenvia-mock-1"


def test_executar_envio_sms_codigo_verificacao_materializa(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.mensageria.api.dto.modelos import CanalMensagem, ResultadoEnvioMensagem
    from app.orquestracao.api.dto.codigo_verificacao_dto import PedidoSmsCodigoVerificacao

    class _TemplatesFake:
        async def obter_por_tipo(self, tipo: str) -> TemplateNotificacao | None:
            assert tipo == CodigoTipoTemplate.CODIGO_VERIFICACAO.value
            return TemplateNotificacao(
                id="t1",
                tipo=tipo,
                email=None,
                sms="Seu código de verificação para BuscaFornecedor é: {{ code }}",
            )

    class _PortaFake:
        def enviar_sms(self, pedido):
            assert pedido.texto == "Seu código de verificação para BuscaFornecedor é: 123456"
            return ResultadoEnvioMensagem(
                id_provedor="sms-codigo-1",
                canal=CanalMensagem.SMS,
            )

    inserir = AsyncMock()
    monkeypatch.setattr(servico, "inserir_ou_atualizar_apos_envio_api", inserir)

    out = asyncio.run(
        servico.executar_envio_sms_codigo_verificacao(
            AsyncMock(),
            PedidoSmsCodigoVerificacao(telefone="5511999999999", codigo="123456"),
            porta=_PortaFake(),
            templates=_TemplatesFake(),
        )
    )

    assert out.id_externo.startswith("codigo-verificacao-")
    assert out.id_provedor == "sms-codigo-1"
    inserir.assert_awaited_once()
    kwargs = inserir.await_args.kwargs
    assert kwargs["tipo_template"] == CodigoTipoTemplate.CODIGO_VERIFICACAO.value
    assert kwargs["contexto"] == {"code": "123456"}


def test_executar_envio_sms_codigo_verificacao_telefone_invalido() -> None:
    from fastapi import HTTPException

    from app.orquestracao.api.dto.codigo_verificacao_dto import PedidoSmsCodigoVerificacao

    with pytest.raises(HTTPException) as ei:
        asyncio.run(
            servico.executar_envio_sms_codigo_verificacao(
                AsyncMock(),
                PedidoSmsCodigoVerificacao(telefone="0800123456", codigo="123456"),
                porta=AsyncMock(),
                templates=AsyncMock(),
            )
        )
    assert ei.value.status_code == 400

"""Testes do endpoint SMS comprador busca WhatsApp."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config.dependencias import obter_porta_envio_mensagem
from app.config.dependencias_templates import obter_porta_templates
from app.main import app
from app.orquestracao.api.dependencias import _pool
from app.orquestracao.api.rotas.comprador_busca_rota import _redis
from app.orquestracao.api.dto.comprador_busca_dto import RespostaSmsCompradorBusca
from app.orquestracao.api.rotas import comprador_busca_rota
from app.orquestracao.servicos import enviar_sms_comprador_busca as servico
from app.templates.modelo import CodigoTipoTemplate, TemplateNotificacao


@pytest.fixture
def client_comprador_busca(monkeypatch: pytest.MonkeyPatch):
    async def _executar(*_a, **_k):
        return RespostaSmsCompradorBusca(
            id_externo="comprador-busca-x",
            id_provedor="zenvia-mock-1",
            status_ultimo="processando",
        )

    monkeypatch.setattr(comprador_busca_rota, "executar_envio_sms_comprador_busca", _executar)
    async def _pool_fake():
        return AsyncMock()

    async def _redis_fake():
        return AsyncMock()

    app.dependency_overrides[_pool] = _pool_fake
    app.dependency_overrides[_redis] = _redis_fake
    app.dependency_overrides[obter_porta_envio_mensagem] = lambda: AsyncMock()

    async def _templates_fake():
        return AsyncMock()

    app.dependency_overrides[obter_porta_templates] = _templates_fake
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_post_comprador_busca_sms_401() -> None:
    with TestClient(app) as client:
        r = client.post(
            "/v1/interno/orquestracao/comprador-busca/sms",
            json={
                "consulta_id": str(uuid.uuid4()),
                "comprador_id": str(uuid.uuid4()),
                "telefone": "5511999999999",
                "url": "https://buscafornecedor.com.br/r/ABC12345",
                "primeira_consulta_sem_cadastro": True,
            },
        )
    assert r.status_code == 401


def test_post_comprador_busca_sms_200(client_comprador_busca: TestClient) -> None:
    r = client_comprador_busca.post(
        "/v1/interno/orquestracao/comprador-busca/sms",
        headers={"X-Api-Key": "test-api-key-unit"},
        json={
            "consulta_id": str(uuid.uuid4()),
            "comprador_id": str(uuid.uuid4()),
            "telefone": "5511999999999",
            "url": "https://buscafornecedor.com.br/r/ABC12345",
            "primeira_consulta_sem_cadastro": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["id_externo"] == "comprador-busca-x"
    assert body["id_provedor"] == "zenvia-mock-1"


def test_executar_envio_sms_comprador_busca_materializa(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.mensageria.api.dto.modelos import CanalMensagem, ResultadoEnvioMensagem
    from app.orquestracao.api.dto.comprador_busca_dto import PedidoSmsCompradorBusca
    from app.orquestracao.servicos.comprador_busca_constantes import id_externo_comprador_busca

    consulta_id = uuid.uuid4()
    comprador_id = uuid.uuid4()

    class _TemplatesFake:
        async def obter_por_tipo(self, tipo: str) -> TemplateNotificacao | None:
            assert tipo == CodigoTipoTemplate.BUSCA_COMPRADOR.value
            return TemplateNotificacao(
                id="t1",
                tipo=tipo,
                email=None,
                sms="BuscaFornecedor: Veja o resultado da sua busca: {{ url }}",
            )

    class _PortaFake:
        def enviar_sms(self, pedido):
            assert "buscafornecedor.com.br" in pedido.texto
            return ResultadoEnvioMensagem(
                id_provedor="sms-comprador-1",
                canal=CanalMensagem.SMS,
            )

    monkeypatch.setattr(servico, "buscar_por_id_externo", AsyncMock(return_value=None))
    monkeypatch.setattr(servico, "inserir_ou_atualizar_apos_envio_api", AsyncMock())
    monkeypatch.setattr(servico, "upsert_apos_envio_sms", AsyncMock())
    monkeypatch.setattr(servico, "_registrar_redis_esperando_confirmacao", AsyncMock())

    out = asyncio.run(
        servico.executar_envio_sms_comprador_busca(
            AsyncMock(),
            AsyncMock(),
            PedidoSmsCompradorBusca(
                consulta_id=consulta_id,
                comprador_id=comprador_id,
                telefone="5511999999999",
                url="https://buscafornecedor.com.br/r/ABC12345",
                primeira_consulta_sem_cadastro=True,
            ),
            porta=_PortaFake(),
            templates=_TemplatesFake(),
        )
    )

    assert out.id_externo == id_externo_comprador_busca(str(consulta_id))
    assert out.id_provedor == "sms-comprador-1"

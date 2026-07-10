"""Testes do endpoint multicanal comprador busca (/enviar)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config.dependencias import obter_porta_envio_mensagem
from app.config.dependencias_templates import obter_porta_templates
from app.main import app
from app.orquestracao.api.dependencias import _pool
from app.orquestracao.api.dto.comprador_busca_dto import RespostaEnviarCompradorBusca
from app.orquestracao.api.rotas import comprador_busca_rota
from app.orquestracao.api.rotas.comprador_busca_rota import _redis
from app.orquestracao.servicos.comprador_busca_constantes import CanalCompradorBusca
from app.orquestracao.servicos.resolver_canal_comprador_busca import resolver_canal_comprador_busca


@pytest.fixture
def client_comprador_busca_enviar(monkeypatch: pytest.MonkeyPatch):
    async def _executar(*_a, **_k):
        return RespostaEnviarCompradorBusca(
            canal=CanalCompradorBusca.SMS,
            id_externo="comprador-busca-x",
            id_provedor="zenvia-mock-1",
            status_ultimo="processando",
        )

    monkeypatch.setattr(comprador_busca_rota, "executar_envio_comprador_busca", _executar)

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


def _corpo_base() -> dict:
    return {
        "consulta_id": str(uuid.uuid4()),
        "comprador_id": str(uuid.uuid4()),
        "telefone": "5511999999999",
        "url": "https://buscafornecedor.com.br/r/ABC12345",
        "primeira_consulta_sem_cadastro": True,
    }


def test_post_comprador_busca_enviar_401() -> None:
    with TestClient(app) as client:
        r = client.post(
            "/v1/interno/orquestracao/comprador-busca/enviar",
            json=_corpo_base(),
        )
    assert r.status_code == 401


def test_post_comprador_busca_enviar_200_sem_canal(client_comprador_busca_enviar: TestClient) -> None:
    r = client_comprador_busca_enviar.post(
        "/v1/interno/orquestracao/comprador-busca/enviar",
        headers={"X-Api-Key": "test-api-key-unit"},
        json=_corpo_base(),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["canal"] == "sms"
    assert body["id_externo"] == "comprador-busca-x"
    assert body["id_provedor"] == "zenvia-mock-1"


def test_post_comprador_busca_enviar_200_com_canal_sms(client_comprador_busca_enviar: TestClient) -> None:
    payload = _corpo_base()
    payload["canal"] = "sms"
    r = client_comprador_busca_enviar.post(
        "/v1/interno/orquestracao/comprador-busca/enviar",
        headers={"X-Api-Key": "test-api-key-unit"},
        json=payload,
    )
    assert r.status_code == 200
    assert r.json()["canal"] == "sms"


def test_resolver_canal_explicito() -> None:
    assert resolver_canal_comprador_busca(CanalCompradorBusca.SMS) == CanalCompradorBusca.SMS


def test_resolver_canal_padrao_sms() -> None:
    assert resolver_canal_comprador_busca(None) == CanalCompradorBusca.SMS

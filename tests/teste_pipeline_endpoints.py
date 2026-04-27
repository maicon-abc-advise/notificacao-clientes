import uuid
import pytest
from fastapi.testclient import TestClient
from app.config.config import obter_configuracao
from app.main import app
from app.reenvio.api.rotas import teste_pipeline as rotas_teste_pipeline

class _PoolFake:
    """Pool mínimo para não depender de schema aplicado no Postgres de teste."""

    async def execute(self, *_args, **_kwargs) -> str:
        return "INSERT 1"

async def _pool_fake() -> _PoolFake:
    return _PoolFake()

def test_teste_pipeline_403_quando_desligado(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TESTE_PIPELINE_HABILITADO", "false")
    obter_configuracao.cache_clear()
    with TestClient(app) as client:
        r = client.post(
            "/v1/interno/teste-pipeline/engajamento",
            headers={"Authorization": "Bearer test-api-key-unit"},
            json={},
        )
    assert r.status_code == 403


def test_teste_pipeline_engajamento_201_quando_habilitado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TESTE_PIPELINE_HABILITADO", "true")
    obter_configuracao.cache_clear()
    uid = str(uuid.uuid4())
    app.dependency_overrides[rotas_teste_pipeline._pool] = _pool_fake
    try:
        with TestClient(app) as client:
            r = client.post(
                "/v1/interno/teste-pipeline/engajamento",
                headers={"Authorization": "Bearer test-api-key-unit"},
                json={"usuario_id": uid},
            )
        assert r.status_code == 201
        assert r.json()["usuario_id"] == uid
    finally:
        app.dependency_overrides.clear()
        monkeypatch.delenv("TESTE_PIPELINE_HABILITADO", raising=False)
        obter_configuracao.cache_clear()

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


def test_teste_pipeline_403_em_producao(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AMBIENTE", "producao")
    monkeypatch.setenv("API_KEY", "test-api-key-unit")
    monkeypatch.setenv("REDIS_URL_PROD", "redis://localhost:6379/0")
    monkeypatch.setenv(
        "DATABASE_URL_PROD",
        "postgresql://notificacao:notificacao_dev@127.0.0.1:5433/notificacao",
    )
    obter_configuracao.cache_clear()
    try:
        with TestClient(app) as client:
            r = client.post(
                "/v1/interno/teste-pipeline/engajamento",
                headers={"Authorization": "Bearer test-api-key-unit"},
                json={},
            )
        assert r.status_code == 403
    finally:
        monkeypatch.delenv("AMBIENTE", raising=False)
        monkeypatch.delenv("REDIS_URL_PROD", raising=False)
        monkeypatch.delenv("DATABASE_URL_PROD", raising=False)
        obter_configuracao.cache_clear()


def test_teste_pipeline_engajamento_201_em_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AMBIENTE", "local")
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
        monkeypatch.delenv("AMBIENTE", raising=False)
        obter_configuracao.cache_clear()

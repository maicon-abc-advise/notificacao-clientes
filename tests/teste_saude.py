"""Testes da rota de saúde."""

from fastapi.testclient import TestClient

from app.main import app


def test_rota_saude() -> None:
    with TestClient(app) as client:
        resposta = client.get("/health")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}

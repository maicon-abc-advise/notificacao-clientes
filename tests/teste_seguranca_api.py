"""API key na rota de teste protegida."""

from fastapi.testclient import TestClient

from app.main import app


def test_sem_api_key_retorna_401() -> None:
    with TestClient(app) as client:
        r = client.get("/v1/ping-autenticado")
    assert r.status_code == 401


def test_api_key_bearer_ok() -> None:
    with TestClient(app) as client:
        r = client.get(
            "/v1/ping-autenticado",
            headers={"Authorization": "Bearer test-api-key-unit"},
        )
    assert r.status_code == 200
    assert r.json() == {"autenticado": True}


def test_api_key_header_x_ok() -> None:
    with TestClient(app) as client:
        r = client.get(
            "/v1/ping-autenticado",
            headers={"X-Api-Key": "test-api-key-unit"},
        )
    assert r.status_code == 200

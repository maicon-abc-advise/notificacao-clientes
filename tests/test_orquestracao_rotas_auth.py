"""Rotas de orquestração: autenticação interna."""

from fastapi.testclient import TestClient

from app.main import app


def test_recebe_consulta_401_sem_api_key() -> None:
    with TestClient(app) as client:
        r = client.post(
            "/v1/interno/orquestracao/recebe-consulta",
            json={
                "id_consulta": "00000000-0000-4000-8000-000000000001",
                "cnpj_basico": "12345678",
                "cnpj_ordem": "0001",
                "cnpj_dv": "00",
            },
        )
    assert r.status_code == 401


def test_verificar_creditos_401_sem_api_key() -> None:
    with TestClient(app) as client:
        r = client.post("/v1/interno/orquestracao/verificar-creditos")
    assert r.status_code == 401


def test_emails_pendentes_lista_401_sem_api_key() -> None:
    with TestClient(app) as client:
        r = client.get("/v1/interno/orquestracao/emails-pendentes")
    assert r.status_code == 401

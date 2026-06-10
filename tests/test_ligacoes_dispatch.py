"""Testes do módulo de ligações (dispatch, fila Redis, webhook)."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app


def test_dispatch_call_exige_api_key():
    client = TestClient(app)
    r = client.post(
        "/v1/calls/dispatch",
        json={
            "customer": {"number": "+5535999999999"},
            "assistantOverrides": {
                "variableValues": {
                    "cnpj_basico": "12345678",
                    "numeroDeBuscas": "3",
                    "ufBuscada": "SP",
                    "segmentoBuscado": "TI",
                },
            },
            "metadata": {"id_externo": str(uuid.uuid4())},
        },
    )
    assert r.status_code == 401


def test_webhook_voice_aceita_payload_minimo():
    from app.orquestracao.api.dependencias import _pool

    pool = AsyncMock()

    async def _fake_pool():
        return pool

    app.dependency_overrides[_pool] = _fake_pool
    try:
        with patch(
            "app.ligacoes.servicos.process_voice_webhook.registrar_evento_se_novo",
            new_callable=AsyncMock,
            return_value=True,
        ):
            with patch(
                "app.ligacoes.servicos.process_voice_webhook.repo_pg.buscar_por_id_chamada_vapi",
                new_callable=AsyncMock,
                return_value=None,
            ):
                with patch(
                    "app.ligacoes.servicos.process_voice_webhook.repo_pg.buscar_por_id_externo",
                    new_callable=AsyncMock,
                    return_value=None,
                ):
                    client = TestClient(app)
                    r = client.post("/v1/webhooks/vapi/voice", json={"message": {"type": "ping"}})
        assert r.status_code == 200
        assert r.json().get("ok") is True
    finally:
        app.dependency_overrides.clear()


def test_n8n_ligacoes_pendentes_exige_api_key():
    client = TestClient(app)
    r = client.get("/v1/interno/n8n/ligacoes-pendentes")
    assert r.status_code == 401


def test_normalizar_telefone_fixo_br():
    from app.ligacoes.servicos.validacao_telefone_voz_br import normalizar_telefone_br_para_voz

    assert normalizar_telefone_br_para_voz("1133334444") == "551133334444"
    assert normalizar_telefone_br_para_voz("+5511999887766") == "5511999887766"


def test_processar_webhook_sem_registro_retorna_200():
    from app.ligacoes.servicos.process_voice_webhook import processar_webhook_voz

    pool = AsyncMock()

    async def _run():
        with patch(
            "app.ligacoes.servicos.process_voice_webhook.registrar_evento_se_novo",
            new_callable=AsyncMock,
            return_value=True,
        ):
            with patch(
                "app.ligacoes.servicos.process_voice_webhook.repo_pg.buscar_por_id_chamada_vapi",
                new_callable=AsyncMock,
                return_value=None,
            ):
                with patch(
                    "app.ligacoes.servicos.process_voice_webhook.repo_pg.buscar_por_id_externo",
                    new_callable=AsyncMock,
                    return_value=None,
                ):
                    return await processar_webhook_voz(
                        pool,
                        {
                            "message": {
                                "type": "status-update",
                                "status": "ringing",
                                "call": {"id": "call-xyz"},
                            },
                        },
                    )

    out = asyncio.run(_run())
    assert out["ok"] is True
    assert out.get("ignorado") == "registro_nao_encontrado"

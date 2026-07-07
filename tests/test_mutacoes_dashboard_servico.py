from __future__ import annotations

from datetime import date, datetime

import pytest
from fastapi import HTTPException

from app.dashboard.servicos import mutacoes_dashboard_servico as m


def test_montar_patch_redis_hash_contexto() -> None:
    body = {"destinatario": "a@b.com", "contexto": {"x": "1"}}
    got = m._montar_patch_redis_hash(body, permitidas=m._WHITELIST_EMAIL_PEND, bloqueadas=m._BLOCK_EMAIL_PEND)
    assert got["destinatario"] == "a@b.com"
    assert '"x"' in got["contexto_json"]


def test_montar_patch_redis_rejeita_id_externo() -> None:
    with pytest.raises(HTTPException) as ei:
        m._montar_patch_redis_hash(
            {"id_externo": "x"},
            permitidas=m._WHITELIST_EMAIL_PEND,
            bloqueadas=m._BLOCK_EMAIL_PEND,
        )
    assert ei.value.status_code == 400


def test_montar_patch_redis_hash_variante_normaliza() -> None:
    got = m._montar_patch_redis_hash(
        {"variante": "elaborado", "experimento_id": "exp-1"},
        permitidas=m._WHITELIST_EMAIL_PEND,
        bloqueadas=m._BLOCK_EMAIL_PEND,
    )
    assert got["variante"] == "elaborado"
    assert got["experimento_id"] == "exp-1"


def test_montar_patch_redis_rejeita_claim_n8n_ativo() -> None:
    with pytest.raises(HTTPException) as ei:
        m._montar_patch_redis_hash(
            {"claim_n8n_ativo": True},
            permitidas=m._WHITELIST_EMAIL_PEND,
            bloqueadas=m._BLOCK_EMAIL_PEND,
        )
    assert ei.value.status_code == 400
    assert "claim_n8n_ativo" in str(ei.value.detail)


def test_valor_sql_param_timestamp_iso_string() -> None:
    dt = m._valor_sql_param(
        "engajamento_atualizado_em",
        "2026-05-12T17:29:07.920332+00:00",
        "timestamp with time zone",
    )
    assert isinstance(dt, datetime)
    assert dt.year == 2026 and dt.month == 5 and dt.day == 12


def test_valor_sql_param_timestamp_z_suffix() -> None:
    dt = m._valor_sql_param("x", "2026-01-01T12:00:00Z", "timestamp with time zone")
    assert isinstance(dt, datetime)
    assert dt.tzinfo is not None


def test_valor_sql_param_date_string() -> None:
    d = m._valor_sql_param("d", "2026-03-15", "date")
    assert isinstance(d, date) and not isinstance(d, datetime)
    assert d.month == 3

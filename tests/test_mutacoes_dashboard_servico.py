from __future__ import annotations

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

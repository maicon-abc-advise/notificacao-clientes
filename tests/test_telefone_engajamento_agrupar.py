"""Testes de agrupamento e constantes de ``telefone_engajamento``."""

from __future__ import annotations

from app.reenvio.repositorios import postgres_telefone_engajamento as repo


def _row(*, telefone: str, canal: str, status: str = "ativo") -> dict[str, object]:
    return {
        "telefone": telefone,
        "canal": canal,
        "status": status,
        "atualizado_em": None,
    }


def test_agrupar_telefone_sem_canal_exibe_canais_vazios():
    rows = [_row(telefone="5511999999999", canal=repo.CANAL_SEM_CANAL, status=repo.STATUS_SEM_STATUS)]
    agrupado = repo._agrupar_linhas_por_telefone(rows)  # noqa: SLF001
    assert len(agrupado) == 1
    assert agrupado[0]["telefone"] == "5511999999999"
    assert agrupado[0]["canais"] == [None, None, None]


def test_agrupar_telefone_com_sms_e_whatsapp():
    rows = [
        _row(telefone="5511888888888", canal=repo.CANAL_SMS, status="sms_entregue"),
        _row(telefone="5511888888888", canal=repo.CANAL_WHATSAPP, status="ativo"),
    ]
    agrupado = repo._agrupar_linhas_por_telefone(rows)  # noqa: SLF001
    assert len(agrupado) == 1
    canais = agrupado[0]["canais"]
    assert canais[0] is not None and canais[0]["canal"] == "sms"
    assert canais[1] is not None and canais[1]["canal"] == "whatsapp"
    assert canais[2] is None

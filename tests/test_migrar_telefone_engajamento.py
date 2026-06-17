"""Migração contatos_sms → telefone_engajamento."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.reenvio.servicos.engajamento_estado import EngajamentoSmsEstado
from app.reenvio.servicos.migrar_contatos_sms_telefone_engajamento import (
    linhas_migracao_sms_de_fornecedor,
    parse_atualizado_em_contato,
)


def test_parse_atualizado_em_contato_iso_z() -> None:
    dt = parse_atualizado_em_contato("2026-06-17T12:00:00Z")
    assert dt.year == 2026
    assert dt.month == 6
    assert dt.tzinfo is not None


def test_linhas_migracao_sms_normaliza_e_ignora_vazio() -> None:
    contatos = [
        {"endereco": "(55) 11 91615-9175", "estado": "sms_entregue", "ultima_atualizacao_em": "2026-01-01T00:00:00Z"},
        {"endereco": "   ", "estado": "ativo"},
        {"endereco": "123", "estado": "ativo"},
    ]
    linhas, ign_sem, ign_inv = linhas_migracao_sms_de_fornecedor("12345678", contatos)
    assert len(linhas) == 1
    assert linhas[0]["telefone"] == "5511916159175"
    assert linhas[0]["status"] == EngajamentoSmsEstado.SMS_ENTREGUE.value
    assert linhas[0]["canal"] == "sms"
    assert linhas[0]["cnpj_basico"] == "12345678"
    assert ign_sem == 1
    assert ign_inv == 1


def test_linhas_migracao_sms_lista_vazia() -> None:
    linhas, ign_sem, ign_inv = linhas_migracao_sms_de_fornecedor("12345678", [])
    assert linhas == []
    assert ign_sem == 0
    assert ign_inv == 0


def test_migrar_telefone_engajamento_401_sem_api_key() -> None:
    with TestClient(app) as client:
        r = client.post("/v1/interno/migrar-telefone-engajamento")
    assert r.status_code == 401

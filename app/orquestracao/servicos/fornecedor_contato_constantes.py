"""Constantes do fluxo e-mail de contato comprador → fornecedor."""

from __future__ import annotations

from uuid import UUID

from app.clique.token_clique import gerar_id_externo_deterministico


def id_externo_fornecedor_contato(consulta_id: UUID, cnpj_basico: str) -> str:
    """Idempotência estável por par (consulta, fornecedor básico)."""
    return gerar_id_externo_deterministico(f"fornecedor-contato:{consulta_id}:{cnpj_basico}")

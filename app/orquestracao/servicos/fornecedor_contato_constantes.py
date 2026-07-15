"""Constantes do fluxo e-mail de contato comprador → fornecedor."""

from __future__ import annotations

from uuid import UUID

from app.clique.token_clique import gerar_id_externo_deterministico


def id_externo_fornecedor_contato(
    cnpj_basico: str,
    *,
    consulta_id: UUID | None = None,
) -> str:
    """Idempotência: ``(consulta, cnpj)`` ou só ``cnpj`` no contato de perfil."""
    if consulta_id is not None:
        return gerar_id_externo_deterministico(
            f"fornecedor-contato:{consulta_id}:{cnpj_basico}"
        )
    return gerar_id_externo_deterministico(f"fornecedor-contato:perfil:{cnpj_basico}")

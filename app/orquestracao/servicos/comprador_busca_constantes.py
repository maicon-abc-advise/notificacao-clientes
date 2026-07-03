"""Constantes do fluxo SMS comprador (busca WhatsApp)."""

from __future__ import annotations

from app.templates.modelo import CodigoTipoTemplate

TIPO_TEMPLATE_BUSCA_COMPRADOR = CodigoTipoTemplate.BUSCA_COMPRADOR.value


def eh_sms_comprador(tipo_template: str | None) -> bool:
    return (tipo_template or "").strip() == TIPO_TEMPLATE_BUSCA_COMPRADOR


def id_externo_comprador_busca(consulta_id: str) -> str:
    return f"comprador-busca-{consulta_id}"

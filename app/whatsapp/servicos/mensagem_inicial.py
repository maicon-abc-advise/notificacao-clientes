"""Templates de mensagem WhatsApp (Cláudia) — 1º contato e follow-up de cadastro."""

from __future__ import annotations

from typing import Any

MESSAGE_TEMPLATE = """Oi, tudo bem?

Vi que vocês atendem o segmento de {segmento}. Estamos com alguns compradores corporativos buscando fornecedores desse nicho na nossa rede esta semana.

Vocês teriam capacidade para receber novos pedidos de cotação atualmente?"""

FOLLOWUP_CADASTRO_TEMPLATE = """Oi, tudo bem?

Passando para saber: você conseguiu fazer o cadastro na BuscaFornecedor?

É gratuito e rapidinho — pelo link 👉 https://buscafornecedor.com.br/fornecedores você ativa o perfil da empresa no segmento de {segmento} e passa a ver as oportunidades do seu nicho.

Se tiver alguma dificuldade no cadastro, me avisa que te ajudo por aqui."""


def _segmento_label(segmento: str | None) -> str:
    return (segmento or "").strip() or "seu segmento"


def montar_mensagem_inicial(segmento: str | None) -> str:
    return MESSAGE_TEMPLATE.format(segmento=_segmento_label(segmento))


def montar_mensagem_followup_cadastro(segmento: str | None) -> str:
    return FOLLOWUP_CADASTRO_TEMPLATE.format(segmento=_segmento_label(segmento))


def row_tem_sucesso_sem_cadastro(row: dict[str, Any] | Any) -> bool:
    for col in ("etapa1", "etapa2", "etapa3"):
        if str(row.get(col) or "").strip().lower() == "sucesso_sem_cadastro":
            return True
    return False


def escolher_mensagem_contato(row: dict[str, Any] | Any, segmento: str | None) -> str:
    """1ª mensagem na abertura; follow-up se já houve ``sucesso_sem_cadastro`` em alguma etapa."""
    if row_tem_sucesso_sem_cadastro(row):
        return montar_mensagem_followup_cadastro(segmento)
    return montar_mensagem_inicial(segmento)

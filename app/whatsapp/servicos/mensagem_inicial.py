"""Template da mensagem inicial WhatsApp (Cláudia)."""

from __future__ import annotations

MESSAGE_TEMPLATE = """Oi, tudo bem?

Vi que vocês atendem o segmento de {segmento}. Estamos com alguns compradores corporativos buscando fornecedores desse nicho na nossa rede esta semana.

Vocês teriam capacidade para receber novos pedidos de cotação atualmente?"""


def montar_mensagem_inicial(segmento: str | None) -> str:
    seg = (segmento or "").strip() or "seu segmento"
    return MESSAGE_TEMPLATE.format(segmento=seg)

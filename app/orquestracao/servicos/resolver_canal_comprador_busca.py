"""Resolução do canal de notificação ao comprador após busca."""

from __future__ import annotations

import random

from app.config.variaveis_sistema.servico import obter_float
from app.orquestracao.servicos.comprador_busca_constantes import CanalCompradorBusca


def resolver_canal_comprador_busca(
    canal_explicito: CanalCompradorBusca | None,
) -> CanalCompradorBusca:
    """Usa o canal do body ou sorteia conforme variáveis do sistema (banco > .env)."""
    if canal_explicito is not None:
        return canal_explicito
    return _sortear_canal_por_configuracao()


def _sortear_canal_por_configuracao() -> CanalCompradorBusca:
    distribuicao = _obter_distribuicao_canais_comprador()
    total = sum(distribuicao.values())
    if total <= 0:
        return CanalCompradorBusca.SMS

    sorteio = random.uniform(0, total)
    acumulado = 0.0
    for canal, peso in distribuicao.items():
        if peso <= 0:
            continue
        acumulado += peso
        if sorteio <= acumulado:
            return canal
    return CanalCompradorBusca.SMS


def _obter_distribuicao_canais_comprador() -> dict[CanalCompradorBusca, float]:
    return {
        CanalCompradorBusca.SMS: obter_float("comprador_pct_sms"),
        CanalCompradorBusca.RCS: obter_float("comprador_pct_rcs"),
        CanalCompradorBusca.WHATSAPP: obter_float("comprador_pct_whatsapp"),
    }

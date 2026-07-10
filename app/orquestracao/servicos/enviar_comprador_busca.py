"""Envio multicanal para comprador após busca (SMS hoje; RCS/WhatsApp futuros)."""

from __future__ import annotations

import asyncpg
from fastapi import HTTPException, status
from redis.asyncio import Redis

from app.mensageria.servicos.porta import PortaEnvioMensagem
from app.orquestracao.api.dto.comprador_busca_dto import (
    PedidoEnviarCompradorBusca,
    PedidoSmsCompradorBusca,
    RespostaEnviarCompradorBusca,
)
from app.orquestracao.servicos.comprador_busca_constantes import CanalCompradorBusca
from app.orquestracao.servicos.enviar_sms_comprador_busca import executar_envio_sms_comprador_busca
from app.orquestracao.servicos.resolver_canal_comprador_busca import resolver_canal_comprador_busca
from app.templates.porta import PortaTemplates


async def executar_envio_comprador_busca(
    pool: asyncpg.Pool,
    redis: Redis,
    pedido: PedidoEnviarCompradorBusca,
    *,
    porta: PortaEnvioMensagem,
    templates: PortaTemplates,
) -> RespostaEnviarCompradorBusca:
    canal = resolver_canal_comprador_busca(pedido.canal)

    if canal == CanalCompradorBusca.SMS:
        resultado = await executar_envio_sms_comprador_busca(
            pool,
            redis,
            PedidoSmsCompradorBusca(
                consulta_id=pedido.consulta_id,
                comprador_id=pedido.comprador_id,
                telefone=pedido.telefone,
                url=pedido.url,
                primeira_consulta_sem_cadastro=pedido.primeira_consulta_sem_cadastro,
            ),
            porta=porta,
            templates=templates,
        )
        return RespostaEnviarCompradorBusca(
            canal=CanalCompradorBusca.SMS,
            id_externo=resultado.id_externo,
            id_provedor=resultado.id_provedor,
            status_ultimo=resultado.status_ultimo,
            idempotente=resultado.idempotente,
        )

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"Canal {canal.value!r} ainda não implementado.",
    )

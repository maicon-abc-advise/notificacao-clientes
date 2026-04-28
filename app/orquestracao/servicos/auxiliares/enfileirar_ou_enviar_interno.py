from __future__ import annotations

from app.mensageria.api.dto.modelos import PedidoEnvioEmail, PedidoEnvioSms
from app.orquestracao.repositorios.redis_emails_pendentes_repo import RepositorioEmailsPendenteRedis
from app.reenvio.repositorios.redis_sms_pendente import RepositorioSmsPendenteRedis
from redis.asyncio import Redis


async def enfileirar_email_pendente(
    redis: Redis,
    pedido: PedidoEnvioEmail,
    *,
    external_id: str,
    origem: str,
) -> bool:
    repo = RepositorioEmailsPendenteRedis()
    return await repo.criar(
        redis,
        external_id=external_id,
        destinatario=pedido.destinatario,
        tipo_template=pedido.tipo_template.value,
        contexto=dict(pedido.contexto),
        remetente=pedido.remetente,
        id_externo=pedido.id_externo,
        telefone_sms_fallback=pedido.telefone_sms_fallback,
        usuario_id=str(pedido.usuario_id) if pedido.usuario_id else None,
        origem=origem,
        consulta_id=pedido.consulta_id,
    )


async def enfileirar_sms_pendente(
    redis: Redis,
    pedido: PedidoEnvioSms,
    *,
    external_id: str,
    origem: str,
) -> bool:
    repo = RepositorioSmsPendenteRedis()
    return await repo.criar(
        redis,
        external_id=external_id,
        telefone=pedido.destinatario,
        tipo_template=pedido.tipo_template.value,
        contexto=dict(pedido.contexto),
        remetente=pedido.remetente,
        origem=origem,
        usuario_id=str(pedido.usuario_id) if pedido.usuario_id else None,
        consulta_id=pedido.consulta_id,
    )

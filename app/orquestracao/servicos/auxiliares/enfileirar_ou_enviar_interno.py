from __future__ import annotations

from app.mensageria.api.dto.modelos import PedidoEnvioEmail, PedidoEnvioSms
from app.orquestracao.repositorios.redis_emails_pendentes_repo import RepositorioEmailsPendenteRedis
from app.reenvio.repositorios.redis_sms_pendente import RepositorioSmsPendenteRedis
from redis.asyncio import Redis


async def enfileirar_email_pendente(
    redis: Redis,
    pedido: PedidoEnvioEmail,
    *,
    id_externo: str,
    origem: str,
) -> bool:
    repo = RepositorioEmailsPendenteRedis()
    return await repo.criar(
        redis,
        id_externo=id_externo,
        destinatario=pedido.destinatario,
        tipo_template=pedido.tipo_template.value,
        contexto=dict(pedido.contexto),
        remetente=pedido.remetente,
        usuario_id=str(pedido.usuario_id) if pedido.usuario_id else None,
        origem=origem,
        telefone_sms_fallback=pedido.telefone_sms_fallback,
        consulta_id=pedido.consulta_id,
    )


async def enfileirar_sms_pendente(
    redis: Redis,
    pedido: PedidoEnvioSms,
    *,
    id_externo: str,
    origem: str,
) -> bool:
    repo = RepositorioSmsPendenteRedis()
    return await repo.criar(
        redis,
        id_externo=id_externo,
        telefone=pedido.destinatario,
        tipo_template=pedido.tipo_template.value,
        contexto=dict(pedido.contexto),
        remetente=pedido.remetente,
        origem=origem,
        usuario_id=str(pedido.usuario_id) if pedido.usuario_id else None,
        consulta_id=pedido.consulta_id,
    )

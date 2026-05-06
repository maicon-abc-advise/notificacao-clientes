from __future__ import annotations

from redis.asyncio import Redis

from app.mensageria.api.dto.modelos import PedidoEnvioEmail, PedidoEnvioSms
from app.orquestracao.repositorios.redis_emails_pendentes_repo import RepositorioEmailsPendenteRedis
from app.reenvio.repositorios.redis_sms_pendente import RepositorioSmsPendenteRedis


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
        fornecedor_id=str(pedido.fornecedor_id) if pedido.fornecedor_id else None,
        cnpj_basico=pedido.cnpj_basico,
        consulta_id=pedido.consulta_id,
        origem=origem,
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
        fornecedor_id=str(pedido.fornecedor_id) if pedido.fornecedor_id else None,
        cnpj_basico=pedido.cnpj_basico,
        consulta_id=pedido.consulta_id,
    )

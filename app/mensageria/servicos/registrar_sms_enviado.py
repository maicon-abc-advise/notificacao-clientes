"""Após envio SMS com sucesso: tira da fila Redis (reenvio) e grava ``sms_enviados`` (Postgres).

A rota de envio vive em ``mensageria``; a persistência do registo de envio fica aqui também.
"""

from __future__ import annotations
import logging
import asyncpg
from redis.asyncio import Redis
from app.mensageria.api.dto.modelos import CanalMensagem, PedidoEnvioSms, ResultadoEnvioMensagem
from app.mensageria.repositorios.postgres_sms_enviados import inserir_ou_atualizar_apos_envio_api
from app.reenvio.repositorios.redis_sms_pendente import RepositorioSmsPendenteRedis
from app.reenvio.servicos.engajamento_estado import EngajamentoSmsEstado
from app.reenvio.servicos.engajamento_fornecedor import tocar_engajamento_sms

_log = logging.getLogger(__name__)


async def registrar_sms_enviado_apos_sucesso(
    pool: asyncpg.Pool,
    redis: Redis,
    pedido: PedidoEnvioSms,
    resultado: ResultadoEnvioMensagem,
) -> None:
    if resultado.canal != CanalMensagem.SMS:
        return
    if not pedido.id_externo:
        return
    msg_id = resultado.id_provedor
    if not msg_id or msg_id.startswith("(sem"):
        _log.warning("SMS sem id Zenvia; não gravado em sms_enviados. id_externo=%s", pedido.id_externo)
        return

    repo = RepositorioSmsPendenteRedis()
    await repo.remover(redis, pedido.id_externo)

    await inserir_ou_atualizar_apos_envio_api(
        pool,
        id_externo=pedido.id_externo,
        telefone=pedido.destinatario,
        tipo_template=pedido.tipo_template.value,
        contexto=dict(pedido.contexto),
        remetente=pedido.remetente,
        id_mensagem_zenvia=msg_id,
        fornecedor_id=pedido.fornecedor_id,
    )
    await tocar_engajamento_sms(pool, pedido.fornecedor_id, EngajamentoSmsEstado.SMS_ENVIADO_API)

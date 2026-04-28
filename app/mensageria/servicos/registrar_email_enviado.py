from __future__ import annotations
import logging
import asyncpg

from app.mensageria.api.dto.modelos import CanalMensagem, PedidoEnvioEmail, ResultadoEnvioMensagem
from app.mensageria.repositorios.postgres_emails_enviados import inserir_ou_atualizar_apos_envio_api

_log = logging.getLogger(__name__)


async def registrar_email_enviado_apos_sucesso(
    pool: asyncpg.Pool,
    pedido: PedidoEnvioEmail,
    resultado: ResultadoEnvioMensagem,
) -> None:
    if resultado.canal != CanalMensagem.EMAIL:
        return
    if not pedido.id_externo:
        return
    msg_id = resultado.id_provedor
    if not msg_id or msg_id.startswith("(sem"):
        _log.warning(
            "E-mail sem id Zenvia; não gravado em emails_enviados. external_id=%s",
            pedido.id_externo,
        )
        return

    await inserir_ou_atualizar_apos_envio_api(
        pool,
        external_id=pedido.id_externo,
        email_destinatario=pedido.destinatario,
        tipo_template=pedido.tipo_template.value,
        contexto=dict(pedido.contexto),
        remetente=pedido.remetente,
        telefone_sms_fallback=pedido.telefone_sms_fallback,
        id_mensagem_zenvia=msg_id,
        usuario_id=pedido.usuario_id,
    )

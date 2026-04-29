from __future__ import annotations
import logging
import time
from app.config.config import obter_configuracao
from app.mensageria.api.dto.modelos import PedidoEnvioEmail, ResultadoEnvioMensagem
from app.reenvio.redis_app import obter_cliente_redis
from app.reenvio.repositorios.redis_emails_esperando_confirmacao import (
    RepositorioEmailsEsperandoConfirmacaoRedis,
)

_log = logging.getLogger(__name__)


async def enfileirar_email_enviado_apos_sucesso(
    pedido: PedidoEnvioEmail,
    resultado: ResultadoEnvioMensagem,
) -> None:
    if not pedido.id_externo:
        _log.warning(
            "E-mail enviado sem id_externo: não foi possível registar em Redis (esperando confirmação).",
        )
        return
    msg_id = resultado.id_provedor
    if not msg_id or msg_id.startswith("(sem"):
        _log.warning(
            "Resposta sem id de mensagem Zenvia: não registado em Redis. id_externo=%s",
            pedido.id_externo,
        )
        return

    cfg = obter_configuracao()
    sweep_ts = int(time.time()) + cfg.sweep_emails_esperando_confirmacao_dias * 86400
    redis = await obter_cliente_redis()
    repo = RepositorioEmailsEsperandoConfirmacaoRedis()
    try:
        await repo.criar_apos_envio(
            redis,
            message_id=msg_id,
            id_externo=pedido.id_externo,
            email_destinatario=pedido.destinatario,
            tipo_template=pedido.tipo_template.value,
            contexto=dict(pedido.contexto),
            remetente=pedido.remetente,
            telefone_sms_fallback=pedido.telefone_sms_fallback,
            sweep_score_ts=sweep_ts,
            usuario_id=str(pedido.usuario_id) if pedido.usuario_id else None,
            consulta_id=pedido.consulta_id,
        )
    except Exception:
        _log.exception(
            "Falha ao registar e-mail no Redis (esperando confirmação). id_externo=%s message_id=%s",
            pedido.id_externo,
            msg_id,
        )

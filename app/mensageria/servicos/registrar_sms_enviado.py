"""Após envio SMS com sucesso: grava ``sms_enviados`` (Postgres) e regista ``sms-esperando-confirmacao`` no Redis.

A fila ``sms-pendente`` não é apagada aqui: o consumidor (ex.: n8n) remove após processar.
A rota de envio vive em ``mensageria``; a persistência do registo de envio fica aqui também.
"""

from __future__ import annotations
import logging
import time

import asyncpg
from redis.asyncio import Redis

from app.config.config import obter_configuracao
from app.mensageria.api.dto.modelos import CanalMensagem, PedidoEnvioSms, ResultadoEnvioMensagem
from app.mensageria.repositorios.postgres_fornecedores import resolver_cnpj_basico_para_envio_mensagem
from app.mensageria.repositorios.postgres_sms_enviados import inserir_ou_atualizar_apos_envio_api
from app.reenvio.repositorios.redis_sms_esperando_confirmacao import RepositorioSmsEsperandoConfirmacaoRedis
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
    cnpj_eng = await resolver_cnpj_basico_para_envio_mensagem(
        pool,
        cnpj_basico=pedido.cnpj_basico,
        fornecedor_id=pedido.fornecedor_id,
    )
    await tocar_engajamento_sms(
        pool,
        pedido.fornecedor_id,
        cnpj_eng,
        EngajamentoSmsEstado.SMS_ENVIADO_API,
        endereco=pedido.destinatario,
        somente_endereco_existente=True,
    )

    cfg = obter_configuracao()
    sweep_ts = int(time.time()) + cfg.sweep_emails_esperando_confirmacao_dias * 86400
    repo_esp = RepositorioSmsEsperandoConfirmacaoRedis()
    try:
        await repo_esp.criar_apos_envio(
            redis,
            message_id=msg_id,
            id_externo=pedido.id_externo,
            telefone_destinatario=pedido.destinatario,
            tipo_template=pedido.tipo_template.value,
            contexto=dict(pedido.contexto),
            remetente=pedido.remetente,
            sweep_score_ts=sweep_ts,
            fornecedor_id=str(pedido.fornecedor_id) if pedido.fornecedor_id else None,
            cnpj_basico=pedido.cnpj_basico,
            consulta_id=pedido.consulta_id,
        )
    except Exception:
        _log.exception(
            "Falha ao registar SMS no Redis (esperando confirmação). id_externo=%s message_id=%s",
            pedido.id_externo,
            msg_id,
        )

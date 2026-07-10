"""Envio SMS para comprador após busca WhatsApp (sem engajamento fornecedor)."""

from __future__ import annotations

import logging
import time

import asyncpg
from fastapi import HTTPException, status
from redis.asyncio import Redis

from app.config.variaveis_sistema.servico import obter_int
from app.mensageria.api.dto.modelos import (
    CanalMensagem,
    PedidoEnvioSms,
    ResultadoEnvioMensagem,
)
from app.mensageria.excecoes.erro import ErroEnvioZenvia
from app.mensageria.repositorios.postgres_sms_enviados import (
    buscar_por_id_externo,
    inserir_ou_atualizar_apos_envio_api,
)
from app.mensageria.servicos.executar_envio_mensagem import id_provedor_valido_para_idempotencia
from app.mensageria.servicos.materializar import materializar_sms
from app.mensageria.servicos.porta import PortaEnvioMensagem
from app.orquestracao.api.dto.comprador_busca_dto import (
    PedidoSmsCompradorBusca,
    RespostaSmsCompradorBusca,
)
from app.orquestracao.repositorios.engajamento_compradores_repo import upsert_apos_envio_sms
from app.orquestracao.servicos.comprador_busca_constantes import (
    id_externo_comprador_busca,
)
from app.reenvio.repositorios.redis_sms_esperando_confirmacao import RepositorioSmsEsperandoConfirmacaoRedis
from app.reenvio.servicos.validacao_telefone_sms_br import (
    MOTIVO_FALHA_SMS_TELEFONE_INVALIDO,
    normalizar_telefone_movel_br_para_sms,
)
from app.templates.modelo import CodigoTipoTemplate
from app.templates.porta import PortaTemplates

_log = logging.getLogger(__name__)


async def executar_envio_sms_comprador_busca(
    pool: asyncpg.Pool,
    redis: Redis,
    pedido: PedidoSmsCompradorBusca,
    *,
    porta: PortaEnvioMensagem,
    templates: PortaTemplates,
) -> RespostaSmsCompradorBusca:
    tel = normalizar_telefone_movel_br_para_sms(pedido.telefone)
    if tel is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=MOTIVO_FALHA_SMS_TELEFONE_INVALIDO,
        )

    id_externo = id_externo_comprador_busca(str(pedido.consulta_id))
    existente = await buscar_por_id_externo(pool, id_externo)
    if existente:
        zid = existente["id_mensagem_zenvia"]
        if id_provedor_valido_para_idempotencia(zid):
            return RespostaSmsCompradorBusca(
                id_externo=id_externo,
                id_provedor=str(zid),
                status_ultimo=(existente["status_ultimo"] or "processando").strip(),
                idempotente=True,
            )

    contexto = {
        "url": pedido.url.strip(),
        "consulta_id": str(pedido.consulta_id),
        "comprador_id": str(pedido.comprador_id),
    }
    pedido_sms = PedidoEnvioSms(
        destinatario=tel,
        tipo_template=CodigoTipoTemplate.BUSCA_COMPRADOR,
        contexto=contexto,
        id_externo=id_externo,
        consulta_id=pedido.consulta_id,
    )

    try:
        materializado = await materializar_sms(pedido_sms, templates)
        resultado = porta.enviar_sms(materializado)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except ErroEnvioZenvia as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e)[:2000],
        ) from e

    msg_id = resultado.id_provedor
    if not id_provedor_valido_para_idempotencia(msg_id):
        _log.warning(
            "SMS comprador sem id Zenvia; não gravado. id_externo=%s consulta=%s",
            id_externo,
            pedido.consulta_id,
        )
        return RespostaSmsCompradorBusca(
            id_externo=id_externo,
            id_provedor=msg_id or "",
            status_ultimo="processando",
        )

    await inserir_ou_atualizar_apos_envio_api(
        pool,
        id_externo=id_externo,
        telefone=tel,
        tipo_template=CodigoTipoTemplate.BUSCA_COMPRADOR.value,
        contexto=contexto,
        remetente=None,
        id_mensagem_zenvia=msg_id,
        fornecedor_id=None,
        cnpj_basico=None,
    )
    await upsert_apos_envio_sms(
        pool,
        telefone=tel,
        comprador_id=pedido.comprador_id,
        primeira_consulta_sem_cadastro=pedido.primeira_consulta_sem_cadastro,
    )
    await _registrar_redis_esperando_confirmacao(redis, pedido_sms, resultado, tel)

    return RespostaSmsCompradorBusca(
        id_externo=id_externo,
        id_provedor=msg_id,
        status_ultimo="processando",
    )


async def _registrar_redis_esperando_confirmacao(
    redis: Redis,
    pedido: PedidoEnvioSms,
    resultado: ResultadoEnvioMensagem,
    telefone: str,
) -> None:
    if resultado.canal != CanalMensagem.SMS or not pedido.id_externo:
        return
    msg_id = resultado.id_provedor
    if not id_provedor_valido_para_idempotencia(msg_id):
        return

    sweep_ts = int(time.time()) + obter_int("sweep_esperando_confirmacao_dias") * 86400
    repo_esp = RepositorioSmsEsperandoConfirmacaoRedis()
    try:
        await repo_esp.criar_apos_envio(
            redis,
            message_id=msg_id,
            id_externo=pedido.id_externo,
            telefone_destinatario=telefone,
            tipo_template=pedido.tipo_template.value,
            contexto=dict(pedido.contexto),
            remetente=pedido.remetente,
            sweep_score_ts=sweep_ts,
            fornecedor_id=None,
            cnpj_basico=None,
            consulta_id=pedido.consulta_id,
        )
    except Exception:
        _log.exception(
            "Falha Redis sms-esperando-confirmacao comprador. id_externo=%s message_id=%s",
            pedido.id_externo,
            msg_id,
        )

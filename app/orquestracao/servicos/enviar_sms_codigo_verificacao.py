"""Envio SMS com código de verificação (sem engajamento fornecedor)."""

from __future__ import annotations

import logging

import asyncpg
from fastapi import HTTPException, status

from app.mensageria.api.dto.modelos import PedidoEnvioSms
from app.mensageria.excecoes.erro import ErroEnvioZenvia
from app.mensageria.repositorios.postgres_sms_enviados import inserir_ou_atualizar_apos_envio_api
from app.mensageria.servicos.executar_envio_mensagem import id_provedor_valido_para_idempotencia
from app.mensageria.servicos.materializar import materializar_sms
from app.mensageria.servicos.porta import PortaEnvioMensagem
from app.orquestracao.api.dto.codigo_verificacao_dto import (
    PedidoSmsCodigoVerificacao,
    RespostaSmsCodigoVerificacao,
)
from app.orquestracao.servicos.codigo_verificacao_constantes import id_externo_codigo_verificacao
from app.reenvio.servicos.validacao_telefone_sms_br import (
    MOTIVO_FALHA_SMS_TELEFONE_INVALIDO,
    normalizar_telefone_movel_br_para_sms,
)
from app.templates.modelo import CodigoTipoTemplate
from app.templates.porta import PortaTemplates

_log = logging.getLogger(__name__)


async def executar_envio_sms_codigo_verificacao(
    pool: asyncpg.Pool,
    pedido: PedidoSmsCodigoVerificacao,
    *,
    porta: PortaEnvioMensagem,
    templates: PortaTemplates,
) -> RespostaSmsCodigoVerificacao:
    tel = normalizar_telefone_movel_br_para_sms(pedido.telefone)
    if tel is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=MOTIVO_FALHA_SMS_TELEFONE_INVALIDO,
        )

    id_externo = id_externo_codigo_verificacao()
    contexto = {"code": pedido.codigo.strip()}
    pedido_sms = PedidoEnvioSms(
        destinatario=tel,
        tipo_template=CodigoTipoTemplate.CODIGO_VERIFICACAO,
        contexto=contexto,
        id_externo=id_externo,
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
            "SMS código verificação sem id Zenvia; não gravado. id_externo=%s telefone=%s",
            id_externo,
            tel,
        )
        return RespostaSmsCodigoVerificacao(
            id_externo=id_externo,
            id_provedor=msg_id or "",
            status_ultimo="processando",
        )

    await inserir_ou_atualizar_apos_envio_api(
        pool,
        id_externo=id_externo,
        telefone=tel,
        tipo_template=CodigoTipoTemplate.CODIGO_VERIFICACAO.value,
        contexto=contexto,
        remetente=None,
        id_mensagem_zenvia=msg_id,
        fornecedor_id=None,
        cnpj_basico=None,
    )

    return RespostaSmsCodigoVerificacao(
        id_externo=id_externo,
        id_provedor=msg_id,
        status_ultimo="processando",
    )

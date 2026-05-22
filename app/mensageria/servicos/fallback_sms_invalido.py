"""Reenfileiramento após telefone SMS inválido na validação pré-provedor (contrato: opção A idempotência Redis)."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Literal

import asyncpg
from redis.asyncio import Redis

from app.clique.token_clique import gerar_id_externo
from app.mensageria.api.dto.modelos import CanalMensagem, PedidoEnvioEmail, PedidoEnvioSms, ResultadoEnvioMensagem
from app.orquestracao.repositorios.engajamento_consulta_repo import carregar_por_cnpj_basico
from app.orquestracao.servicos.auxiliares.decidir_canal_e_cadencia import (
    email_usavel_para_notificacao,
    telefone_usavel_para_sms,
)
from app.orquestracao.servicos.auxiliares.enfileirar_ou_enviar_interno import (
    enfileirar_email_pendente,
    enfileirar_sms_pendente,
)
from app.reenvio.repositorios.redis_consulta_notificacao import (
    fase_pendente_sms,
    liberar_trava_se_fase,
)
from app.reenvio.servicos.engajamento_contatos import (
    agregado_canal_bloqueado,
    estado_granular_email,
    estado_granular_sms,
    normalizar_telefone,
    proximo_email_tentavel_apos_contato,
    proximo_telefone_tentavel_apos_contato,
)
from app.reenvio.servicos.validacao_telefone_sms_br import MOTIVO_FALHA_SMS_TELEFONE_INVALIDO, normalizar_telefone_movel_br_para_sms
from app.templates.modelo import CodigoTipoTemplate

_log = logging.getLogger(__name__)

ID_PROVEDOR_REENFILEIRADO = "(reenfileirado-fila)"
_REDIS_PREFIX = "v1:mensagens:sms-invalid-fallback:"
_REDIS_TTL_SEG = 30 * 24 * 3600
_ORIGEM = "sms_invalido_fallback"


def _redis_key(id_externo: str) -> str:
    return f"{_REDIS_PREFIX}{id_externo}"


def resultado_reenfileirado(
    *,
    canal_efetivo: Literal["email", "sms"],
    id_externo_pedido_original: str | None,
    id_externo_novo: str,
    idempotente: bool = False,
) -> ResultadoEnvioMensagem:
    canal = CanalMensagem.EMAIL if canal_efetivo == "email" else CanalMensagem.SMS
    part: dict[str, Any] = {
        "acao": "reenfileirado_apos_telefone_invalido",
        "canal_efetivo": canal_efetivo,
        "id_externo_pedido_original": id_externo_pedido_original,
        "id_externo_novo": id_externo_novo,
        "motivo": MOTIVO_FALHA_SMS_TELEFONE_INVALIDO,
    }
    if idempotente:
        part["idempotente"] = True
    return ResultadoEnvioMensagem(
        id_provedor=ID_PROVEDOR_REENFILEIRADO,
        canal=canal,
        resposta_parcial=part,
    )


async def ler_replay_idempotencia(redis: Redis, id_externo: str) -> ResultadoEnvioMensagem | None:
    raw = await redis.get(_redis_key(id_externo))
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    canal = data.get("canal")
    id_novo = (data.get("id_externo_novo") or "").strip()
    if canal not in ("email", "sms") or not id_novo:
        return None
    return resultado_reenfileirado(
        canal_efetivo=canal,
        id_externo_pedido_original=id_externo,
        id_externo_novo=id_novo,
        idempotente=True,
    )


async def gravar_idempotencia_fallback(
    redis: Redis,
    id_externo_pedido: str,
    *,
    canal_efetivo: Literal["email", "sms"],
    id_externo_novo: str,
) -> None:
    payload = json.dumps(
        {"canal": canal_efetivo, "id_externo_novo": id_externo_novo},
        ensure_ascii=False,
    )
    await redis.set(_redis_key(id_externo_pedido), payload, ex=_REDIS_TTL_SEG)


def _proximo_sms_valido_engajamento(
    contatos_sms: list,
    telefone_pedido_norm: str | None,
) -> str | None:
    """Primeiro telefone tentável na ordem do engajamento que passe validação móvel BR."""
    cur: str | None = telefone_pedido_norm
    vistos: set[str] = set()
    while True:
        nxt = proximo_telefone_tentavel_apos_contato(contatos_sms, cur)
        if not nxt:
            return None
        n_norm = normalizar_telefone(nxt)
        if not n_norm or n_norm in vistos:
            return None
        vistos.add(n_norm)
        canon = normalizar_telefone_movel_br_para_sms(nxt)
        if not canon:
            cur = nxt
            continue
        st = estado_granular_sms(contatos_sms, nxt)
        if not telefone_usavel_para_sms(nxt, st):
            cur = nxt
            continue
        return canon


async def tentar_reenfileirar_apos_sms_invalido(
    pool: asyncpg.Pool,
    redis: Redis,
    pedido: PedidoEnvioSms,
    *,
    cnpj_eng: str,
) -> tuple[Literal["email", "sms"], str] | None:
    snap = await carregar_por_cnpj_basico(pool, cnpj_eng)

   
    if pedido.id_externo and pedido.consulta_id:
        cnpj_lo = (pedido.cnpj_basico or "").strip()
        if len(cnpj_lo) == 8:
            await liberar_trava_se_fase(
                redis,
                pedido.consulta_id,
                cnpj_lo,
                fase_pendente_sms(pedido.id_externo),
            )

    if not agregado_canal_bloqueado(snap.engajamento_email):
        em = proximo_email_tentavel_apos_contato(snap.contatos_email, None)
        if em:
            st_e = estado_granular_email(snap.contatos_email, em)
            if email_usavel_para_notificacao(em, estado_granular=st_e):
                tipo = (
                    CodigoTipoTemplate.APARECEU_BUSCA
                    if pedido.fornecedor_id
                    else CodigoTipoTemplate.APARECEU_BUSCA_SEM_REGISTRO
                )
                base_ext = pedido.id_externo or gerar_id_externo()
                novo = (
                    f"{base_ext}:fallback_email:{uuid.uuid4().hex[:12]}"
                    if pedido.id_externo
                    else gerar_id_externo()
                )
                pedido_e = PedidoEnvioEmail(
                    destinatario=em,
                    tipo_template=tipo,
                    contexto=dict(pedido.contexto),
                    remetente=pedido.remetente,
                    id_externo=novo,
                    fornecedor_id=pedido.fornecedor_id,
                    cnpj_basico=pedido.cnpj_basico,
                    consulta_id=pedido.consulta_id,
                )
                if await enfileirar_email_pendente(redis, pedido_e, id_externo=novo, origem=_ORIGEM):
                    _log.info(
                        "SMS inválido: reenfileirado e-mail id_externo_novo=%s dest=%s",
                        novo,
                        em,
                    )
                    return ("email", novo)

    if not agregado_canal_bloqueado(snap.engajamento_sms):
        tel_ctx = normalizar_telefone(pedido.destinatario) or None
        prox_c = _proximo_sms_valido_engajamento(snap.contatos_sms, tel_ctx)
        if prox_c:
            base_ext = pedido.id_externo or gerar_id_externo()
            novo = (
                f"{base_ext}:fallback_sms:{uuid.uuid4().hex[:12]}"
                if pedido.id_externo
                else gerar_id_externo()
            )
            pedido_s = PedidoEnvioSms(
                destinatario=prox_c,
                tipo_template=pedido.tipo_template,
                contexto=dict(pedido.contexto),
                remetente=pedido.remetente,
                id_externo=novo,
                fornecedor_id=pedido.fornecedor_id,
                cnpj_basico=pedido.cnpj_basico,
                consulta_id=pedido.consulta_id,
            )
            if await enfileirar_sms_pendente(redis, pedido_s, id_externo=novo, origem=_ORIGEM):
                _log.info(
                    "SMS inválido: reenfileirado SMS id_externo_novo=%s dest=%s",
                    novo,
                    prox_c,
                )
                return ("sms", novo)

    return None

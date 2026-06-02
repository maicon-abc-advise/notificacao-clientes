"""Envio de e-mail/SMS (lógica compartilhada entre API interna e dashboard)."""

from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import HTTPException, status
from redis.asyncio import Redis

from app.mensageria.api.dto.modelos import (
    CanalMensagem,
    PedidoEnvioEmail,
    PedidoEnvioSms,
    ResultadoEnvioMensagem,
)
from app.mensageria.excecoes.erro import ErroEnvioZenvia
from app.mensageria.repositorios.postgres_emails_enviados import buscar_por_id_externo as buscar_email_por_id_externo
from app.mensageria.repositorios.postgres_fornecedores import (
    fornecedor_id_existe,
    resolver_cnpj_basico_para_envio_mensagem,
)
from app.mensageria.repositorios.postgres_sms_enviados import (
    buscar_por_id_externo as buscar_sms_por_id_externo,
    inserir_ou_atualizar_falha_validacao_telefone_sms,
)
from app.mensageria.servicos.fallback_sms_invalido import (
    gravar_idempotencia_fallback,
    ler_replay_idempotencia,
    resultado_reenfileirado,
    tentar_reenfileirar_apos_sms_invalido,
)
from app.mensageria.servicos.materializar import materializar_email, materializar_sms
from app.mensageria.servicos.porta import PortaEnvioMensagem
from app.mensageria.servicos.registrar_email_enviado import registrar_email_enviado_apos_sucesso
from app.mensageria.servicos.registrar_sms_enviado import registrar_sms_enviado_apos_sucesso
from app.reenvio.servicos.enfileirar_apos_envio_email import enfileirar_email_enviado_apos_sucesso
from app.reenvio.servicos.engajamento_contatos import normalizar_telefone
from app.reenvio.servicos.engajamento_estado import EngajamentoEmailEstado, EngajamentoSmsEstado
from app.reenvio.servicos.engajamento_fornecedor import (
    exigir_destinatario_no_engajamento_email,
    exigir_destinatario_no_engajamento_sms,
    tocar_engajamento_email,
    tocar_engajamento_sms,
)
from app.reenvio.servicos.validacao_telefone_sms_br import (
    MOTIVO_FALHA_SMS_TELEFONE_INVALIDO,
    normalizar_telefone_movel_br_para_sms,
)
from app.templates.porta import PortaTemplates


def id_provedor_valido_para_idempotencia(id_z: str | None) -> bool:
    if not id_z:
        return False
    s = str(id_z).strip()
    return bool(s) and not s.startswith("(sem")


async def garantir_fornecedor_cadastrado(
    pool: asyncpg.Pool,
    fornecedor_id: UUID | None,
    cnpj_basico: str | None,
) -> None:
    if fornecedor_id is None:
        if not (cnpj_basico or "").strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="informe fornecedor_id ou cnpj_basico",
            )
        return
    if not await fornecedor_id_existe(pool, fornecedor_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="fornecedor não encontrado",
        )


async def validar_engajamento_antes_envio_email(pool: asyncpg.Pool, pedido: PedidoEnvioEmail) -> str:
    cnpj = await resolver_cnpj_basico_para_envio_mensagem(
        pool,
        cnpj_basico=pedido.cnpj_basico,
        fornecedor_id=pedido.fornecedor_id,
    )
    await exigir_destinatario_no_engajamento_email(
        pool,
        cnpj_basico=cnpj,
        destinatario=pedido.destinatario,
    )
    return cnpj


async def executar_envio_email(
    pool: asyncpg.Pool,
    pedido: PedidoEnvioEmail,
    *,
    porta: PortaEnvioMensagem,
    templates: PortaTemplates,
) -> ResultadoEnvioMensagem:
    if pedido.id_externo:
        existente = await buscar_email_por_id_externo(pool, pedido.id_externo)
        zid = existente["id_mensagem_zenvia"] if existente else None
        if id_provedor_valido_para_idempotencia(zid):
            return ResultadoEnvioMensagem(
                id_provedor=str(zid),
                canal=CanalMensagem.EMAIL,
                resposta_parcial={"idempotente": True},
            )
    await garantir_fornecedor_cadastrado(pool, pedido.fornecedor_id, pedido.cnpj_basico)
    cnpj_eng = await validar_engajamento_antes_envio_email(pool, pedido)
    materializado = await materializar_email(pedido, templates)
    resultado = porta.enviar_email(materializado)
    await enfileirar_email_enviado_apos_sucesso(pedido, resultado)
    await registrar_email_enviado_apos_sucesso(pool, pedido, resultado, cnpj_basico_resolvido=cnpj_eng)
    await tocar_engajamento_email(
        pool,
        pedido.fornecedor_id,
        cnpj_eng,
        EngajamentoEmailEstado.EMAIL_ENVIADO_API,
        endereco=pedido.destinatario,
        somente_endereco_existente=True,
    )
    return resultado


async def executar_envio_sms(
    pool: asyncpg.Pool,
    redis: Redis,
    pedido: PedidoEnvioSms,
    *,
    porta: PortaEnvioMensagem,
    templates: PortaTemplates,
) -> ResultadoEnvioMensagem:
    if pedido.id_externo:
        existente = await buscar_sms_por_id_externo(pool, pedido.id_externo)
        if existente:
            zid = existente["id_mensagem_zenvia"]
            if id_provedor_valido_para_idempotencia(zid):
                return ResultadoEnvioMensagem(
                    id_provedor=str(zid),
                    canal=CanalMensagem.SMS,
                    resposta_parcial={"idempotente": True},
                )
            if (existente["status_ultimo"] or "").strip() == "falha_definitiva" and (
                (existente.get("motivo_ultimo_evento") or "").strip() == MOTIVO_FALHA_SMS_TELEFONE_INVALIDO
            ):
                if pedido.id_externo:
                    replay = await ler_replay_idempotencia(redis, pedido.id_externo)
                    if replay:
                        return replay
    await garantir_fornecedor_cadastrado(pool, pedido.fornecedor_id, pedido.cnpj_basico)
    cnpj_eng = await resolver_cnpj_basico_para_envio_mensagem(
        pool,
        cnpj_basico=pedido.cnpj_basico,
        fornecedor_id=pedido.fornecedor_id,
    )
    if normalizar_telefone_movel_br_para_sms(pedido.destinatario) is None:
        await tocar_engajamento_sms(
            pool,
            pedido.fornecedor_id,
            cnpj_eng,
            EngajamentoSmsEstado.SMS_NUMERO_INVALIDO,
            endereco=pedido.destinatario,
        )
        if pedido.id_externo:
            await inserir_ou_atualizar_falha_validacao_telefone_sms(
                pool,
                id_externo=pedido.id_externo,
                telefone=normalizar_telefone(pedido.destinatario) or (pedido.destinatario or "")[:500],
                tipo_template=pedido.tipo_template.value,
                contexto=dict(pedido.contexto),
                remetente=pedido.remetente,
                fornecedor_id=pedido.fornecedor_id,
                cnpj_basico=cnpj_eng,
                motivo=MOTIVO_FALHA_SMS_TELEFONE_INVALIDO,
            )
            replay = await ler_replay_idempotencia(redis, pedido.id_externo)
            if replay:
                return replay
        fb = await tentar_reenfileirar_apos_sms_invalido(pool, redis, pedido, cnpj_eng=cnpj_eng)
        if fb:
            canal_e, id_novo = fb
            if pedido.id_externo:
                await gravar_idempotencia_fallback(
                    redis,
                    pedido.id_externo,
                    canal_efetivo=canal_e,
                    id_externo_novo=id_novo,
                )
            return resultado_reenfileirado(
                canal_efetivo=canal_e,
                id_externo_pedido_original=pedido.id_externo,
                id_externo_novo=id_novo,
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=MOTIVO_FALHA_SMS_TELEFONE_INVALIDO,
        )
    await exigir_destinatario_no_engajamento_sms(
        pool,
        cnpj_basico=cnpj_eng,
        destinatario=pedido.destinatario,
    )
    materializado = await materializar_sms(pedido, templates)
    resultado = porta.enviar_sms(materializado)
    await registrar_sms_enviado_apos_sucesso(pool, redis, pedido, resultado)
    return resultado

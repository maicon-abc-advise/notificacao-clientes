"""Cenários de teste locais: simular envio e-mail/SMS **sem** Zenvia e exercitar Redis + Postgres.

Só responde com ``AMBIENTE=local`` (em ``producao`` as rotas não são expostas).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from redis.asyncio import Redis

from app.config.config import Configuracao, obter_configuracao
from app.iam.dependencias import verificar_chamada_interna
from app.mensageria.api.dto.modelos import (
    CanalMensagem,
    PedidoEnvioEmail,
    PedidoEnvioSms,
    ResultadoEnvioMensagem,
)
from app.reenvio.api.dependencias_teste_pipeline import exigir_teste_pipeline_habilitado
from app.reenvio.api.dto.webhook_zenvia import WebhookMessageStatusZenvia
from app.reenvio.redis_app import obter_cliente_redis
from app.reenvio.servicos.enfileirar_apos_envio_email import enfileirar_email_enviado_apos_sucesso
from app.reenvio.servicos.engajamento_estado import EngajamentoEmailEstado, EngajamentoSmsEstado
from app.reenvio.servicos.engajamento_usuario import tocar_engajamento_email
from app.reenvio.servicos.processar_status_email import processar_webhook_status_email
from app.mensageria.servicos.registrar_email_enviado import registrar_email_enviado_apos_sucesso
from app.mensageria.servicos.registrar_sms_enviado import registrar_sms_enviado_apos_sucesso
from app.templates.modelo import CodigoTipoTemplate
from app.templates.conexao import obter_pool

router = APIRouter(
    prefix="/v1/interno/teste-pipeline",
    tags=["teste-pipeline"],
    dependencies=[
        Depends(verificar_chamada_interna),
        Depends(exigir_teste_pipeline_habilitado),
    ],
)


async def _pool() -> asyncpg.Pool:
    return await obter_pool()


async def _redis() -> Redis:
    return await obter_cliente_redis()


class EngajamentoSeedCorpo(BaseModel):
    usuario_id: UUID | None = Field(
        default=None,
        description="Se omitido, gera um UUID novo.",
    )
    engajamento_email: EngajamentoEmailEstado = Field(default=EngajamentoEmailEstado.ATIVO)
    engajamento_sms: EngajamentoSmsEstado = Field(default=EngajamentoSmsEstado.ATIVO)


@router.post(
    "/engajamento",
    status_code=status.HTTP_201_CREATED,
    summary="Insere (ou garante) uma linha em engajamento_usuarios para testes",
)
async def post_seed_engajamento(
    corpo: EngajamentoSeedCorpo,
    pool: Annotated[asyncpg.Pool, Depends(_pool)],
) -> dict[str, Any]:
    uid = corpo.usuario_id or uuid.uuid4()
    await pool.execute(
        """
        INSERT INTO public.engajamento_usuarios (
            usuario_id, engajamento_email, engajamento_sms,
            engajamento_email_atualizado_em, engajamento_sms_atualizado_em, engajamento_atualizado_em
        )
        VALUES ($1, $2, $3, now(), now(), now())
        ON CONFLICT (usuario_id) DO UPDATE SET
            engajamento_email = EXCLUDED.engajamento_email,
            engajamento_sms = EXCLUDED.engajamento_sms,
            engajamento_email_atualizado_em = now(),
            engajamento_sms_atualizado_em = now(),
            engajamento_atualizado_em = now()
        """,
        uid,
        corpo.engajamento_email.value[:64],
        corpo.engajamento_sms.value[:64],
    )
    return {
        "usuario_id": str(uid),
        "engajamento_email": corpo.engajamento_email.value,
        "engajamento_sms": corpo.engajamento_sms.value,
    }


class SimularEmailCorpo(BaseModel):
    destinatario: str = Field(..., min_length=3)
    id_externo: str = Field(..., min_length=1, max_length=64)
    usuario_id: UUID | None = None
    telefone_sms_fallback: str | None = Field(
        default=None,
        max_length=20,
        description="E.164 — recomendado para testar bounce ou sweep depois.",
    )
    tipo_template: CodigoTipoTemplate = CodigoTipoTemplate.APARECEU_BUSCA
    contexto: dict[str, str] = Field(default_factory=dict)
    remetente: str | None = Field(default=None, max_length=64)
    message_id_falso: str | None = Field(
        default=None,
        description="Simula o messageId da Zenvia; usado no Redis e emails_enviados.",
    )
    tocar_engajamento_api: bool = Field(
        default=True,
        description="Se true, chama tocar_engajamento_email após o registo (como a API real).",
    )


@router.post(
    "/simular-email-enviado",
    status_code=status.HTTP_200_OK,
    summary="Sem Zenvia: enfileira Redis + emails_enviados (+ engajamento opcional)",
)
async def post_simular_email_enviado(
    corpo: SimularEmailCorpo,
    pool: Annotated[asyncpg.Pool, Depends(_pool)],
) -> dict[str, Any]:
    msg_id = corpo.message_id_falso or f"test-email-{uuid.uuid4().hex[:24]}"
    pedido = PedidoEnvioEmail(
        destinatario=corpo.destinatario,
        tipo_template=corpo.tipo_template,
        contexto=corpo.contexto,
        remetente=corpo.remetente,
        id_externo=corpo.id_externo,
        telefone_sms_fallback=corpo.telefone_sms_fallback,
        usuario_id=corpo.usuario_id,
    )
    resultado = ResultadoEnvioMensagem(
        id_provedor=msg_id,
        canal=CanalMensagem.EMAIL,
        resposta_parcial={"teste": True},
    )
    await enfileirar_email_enviado_apos_sucesso(pedido, resultado)
    await registrar_email_enviado_apos_sucesso(pool, pedido, resultado)
    if corpo.tocar_engajamento_api:
        await tocar_engajamento_email(pool, corpo.usuario_id, EngajamentoEmailEstado.EMAIL_ENVIADO_API)
    return {
        "message_id_zenvia_falso": msg_id,
        "id_externo": corpo.id_externo,
        "redis_chave_hash": f"emails-esperando-confirmacao:{msg_id}",
        "emails_enviados": "upsert por id_externo",
        "usuario_id": str(corpo.usuario_id) if corpo.usuario_id else None,
    }


_CodigoWebhookEmail = Literal["REJECTED", "SENT", "DELIVERED", "NOT_DELIVERED", "READ"]


class WebhookEmailSinteticoCorpo(BaseModel):
    message_id: str = Field(..., min_length=1, description="Deve ser o messageId guardado no Redis (ex.: do passo simular-email).")
    code: _CodigoWebhookEmail
    cause: str | None = None
    description: str | None = None
    id_evento: str | None = Field(
        default=None,
        description="Id único do evento (idempotência). Novo UUID se omitido.",
    )


@router.post(
    "/disparar-webhook-email",
    status_code=status.HTTP_200_OK,
    summary="Monta um MESSAGE_STATUS e chama processar_webhook_status_email",
)
async def post_disparar_webhook_email(
    corpo: WebhookEmailSinteticoCorpo,
    pool: Annotated[asyncpg.Pool, Depends(_pool)],
    redis: Annotated[Redis, Depends(_redis)],
    config: Annotated[Configuracao, Depends(obter_configuracao)],
) -> dict[str, Any]:
    evt = corpo.id_evento or f"test-evt-{uuid.uuid4().hex}"
    payload = WebhookMessageStatusZenvia.model_validate(
        {
            "id": evt,
            "timestamp": "2026-01-01T12:00:00Z",
            "type": "MESSAGE_STATUS",
            "subscriptionId": "test-sub",
            "channel": "email",
            "messageId": corpo.message_id,
            "contentIndex": 0,
            "messageStatus": {
                "timestamp": "2026-01-01T12:00:01Z",
                "code": corpo.code,
                "cause": corpo.cause,
                "description": corpo.description,
            },
        }
    )
    out = await processar_webhook_status_email(pool, redis, config, payload)
    return {"payload_id_evento": evt, "resultado": out}


class SimularSmsCorpo(BaseModel):
    id_externo: str = Field(..., min_length=1, max_length=64)
    destinatario: str = Field(..., min_length=5, max_length=20)
    tipo_template: CodigoTipoTemplate = CodigoTipoTemplate.CONSULTADO_SEM_EMAIL
    contexto: dict[str, str] = Field(default_factory=dict)
    remetente: str | None = Field(default=None, max_length=64)
    usuario_id: UUID | None = None
    id_mensagem_zenvia_falso: str | None = Field(
        default=None,
        description="Senão, gera test-sms-{uuid}.",
    )


@router.post(
    "/simular-sms-enviado",
    status_code=status.HTTP_200_OK,
    summary="Sem Zenvia: remove sms-pendente:* se existir e grava sms_enviados",
)
async def post_simular_sms_enviado(
    corpo: SimularSmsCorpo,
    pool: Annotated[asyncpg.Pool, Depends(_pool)],
    redis: Annotated[Redis, Depends(_redis)],
) -> dict[str, Any]:
    zid = corpo.id_mensagem_zenvia_falso or f"test-sms-{uuid.uuid4().hex[:16]}"
    pedido = PedidoEnvioSms(
        destinatario=corpo.destinatario,
        tipo_template=corpo.tipo_template,
        contexto=corpo.contexto,
        remetente=corpo.remetente,
        id_externo=corpo.id_externo,
        usuario_id=corpo.usuario_id,
    )
    resultado = ResultadoEnvioMensagem(
        id_provedor=zid,
        canal=CanalMensagem.SMS,
        resposta_parcial={"teste": True},
    )
    await registrar_sms_enviado_apos_sucesso(pool, redis, pedido, resultado)
    return {
        "id_mensagem_zenvia_falso": zid,
        "id_externo": corpo.id_externo,
        "sms_enviados": "upsert",
        "usuario_id": str(corpo.usuario_id) if corpo.usuario_id else None,
    }


class CenarioBounceSmsCorpo(BaseModel):
    """Email falso + bounce hard com cause que dispara SMS na fila sms-pendente (Redis)."""

    destinatario: str = Field(default="teste@exemplo.com", min_length=3)
    id_externo: str = Field(default="teste-pipeline-negocio", max_length=64)
    usuario_id: UUID | None = None
    telefone_sms_fallback: str = Field(..., min_length=8, max_length=20)
    cause_bounce: str = Field(
        default="550 invalid recipient",
        description="Precisa casar com classificar_falha_email → HARD_BOUNCE.",
    )


@router.post(
    "/cenario-email-bounce-gera-sms-redis",
    status_code=status.HTTP_200_OK,
    summary="Orquestra: simular-email + webhook NOT_DELIVERED (hard bounce) → SMS na fila",
)
async def post_cenario_bounce_para_sms(
    corpo: CenarioBounceSmsCorpo,
    pool: Annotated[asyncpg.Pool, Depends(_pool)],
    redis: Annotated[Redis, Depends(_redis)],
    config: Annotated[Configuracao, Depends(obter_configuracao)],
) -> dict[str, Any]:
    msg_id = f"test-email-{uuid.uuid4().hex[:24]}"
    pedido = PedidoEnvioEmail(
        destinatario=corpo.destinatario,
        tipo_template=CodigoTipoTemplate.APARECEU_BUSCA,
        contexto={},
        remetente=None,
        id_externo=corpo.id_externo,
        telefone_sms_fallback=corpo.telefone_sms_fallback,
        usuario_id=corpo.usuario_id,
    )
    resultado = ResultadoEnvioMensagem(
        id_provedor=msg_id,
        canal=CanalMensagem.EMAIL,
        resposta_parcial={"teste": True, "cenario": "bounce_sms"},
    )
    await enfileirar_email_enviado_apos_sucesso(pedido, resultado)
    await registrar_email_enviado_apos_sucesso(pool, pedido, resultado)
    await tocar_engajamento_email(pool, corpo.usuario_id, EngajamentoEmailEstado.EMAIL_ENVIADO_API)

    evt = f"test-evt-bounce-{uuid.uuid4().hex}"
    payload = WebhookMessageStatusZenvia.model_validate(
        {
            "id": evt,
            "timestamp": "2026-01-01T12:00:00Z",
            "type": "MESSAGE_STATUS",
            "subscriptionId": "test-sub",
            "channel": "email",
            "messageId": msg_id,
            "contentIndex": 0,
            "messageStatus": {
                "timestamp": "2026-01-01T12:00:01Z",
                "code": "NOT_DELIVERED",
                "cause": corpo.cause_bounce,
                "description": "synthetic bounce for local test",
            },
        }
    )
    webhook_out = await processar_webhook_status_email(pool, redis, config, payload)
    return {
        "message_id_zenvia_falso": msg_id,
        "id_externo_email": corpo.id_externo,
        "id_evento_webhook": evt,
        "webhook_resultado": webhook_out,
        "dica": "Veja sms-pendente:* no Redis ou GET /v1/interno/sms-pendentes se bounce_sms_enfileirado.",
    }

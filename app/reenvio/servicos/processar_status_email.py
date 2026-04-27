"""Regras de negócio do webhook de **e-mail**: atualiza Redis e enfileira SMS pendente no Redis."""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

import asyncpg
from redis.asyncio import Redis

from app.config.config import Configuracao
from app.reenvio.api.dto.webhook_zenvia import WebhookMessageStatusZenvia
from app.reenvio.repositorios.postgres_webhook_eventos import registrar_evento_se_novo
from app.reenvio.repositorios.redis_email_pendente import RepositorioEmailPendenteRedis
from app.reenvio.repositorios.redis_sms_pendente import RepositorioSmsPendenteRedis
from app.reenvio.servicos.classificar_cause_email import (
    ResultadoClassificacaoEmail,
    classificar_falha_email,
)
from app.reenvio.servicos.engajamento_usuario import parse_usuario_id, tocar_engajamento

_log = logging.getLogger(__name__)

TEMPLATE_SMS_EMAIL_INVALIDO = "CONSULTADO_SEM_EMAIL"


def _contexto_sms_de_hash(campos: dict[str, str]) -> dict[str, str]:
    base = json.loads(campos.get("contexto_json") or "{}")
    if not isinstance(base, dict):
        base = {}
    out: dict[str, str] = {str(k): str(v) for k, v in base.items() if v is not None}
    out.setdefault("url_plataforma", "https://plataforma.local")
    return out


async def processar_webhook_status_email(
    pool: asyncpg.Pool,
    redis: Redis,
    cfg: Configuracao,
    payload: WebhookMessageStatusZenvia,
) -> dict[str, Any]:
    if payload.channel != "email":
        return {"acao": "ignorado", "motivo": "canal não é email"}

    novo = await registrar_evento_se_novo(pool, payload.id)
    if not novo:
        return {"acao": "duplicado", "id_evento": payload.id}

    repo = RepositorioEmailPendenteRedis()
    message_id = payload.messageId
    code = payload.messageStatus.code
    cause = payload.messageStatus.cause
    description = payload.messageStatus.description

    dados = await repo.obter(redis, message_id)
    if not dados:
        _log.info(
            "Webhook e-mail sem hash Redis (message_id=%s). Pode ser envio antigo ou teste.",
            message_id,
        )
        return {"acao": "sem_pendente_redis", "message_id": message_id, "code": code}

    uid = parse_usuario_id(dados.get("usuario_id"))

    if code == "READ":
        await tocar_engajamento(pool, uid, "email_lido")
        await repo.remover(redis, message_id)
        return {"acao": "removido_fila", "message_id": message_id, "code": code}

    if code == "SENT":
        await tocar_engajamento(pool, uid, "email_webhook_sent")
        await repo.atualizar_campos(redis, message_id, {"status_atual": "ENVIADO_PROVEDOR"})
        return {"acao": "atualizado", "message_id": message_id, "code": code}

    if code == "DELIVERED":
        await tocar_engajamento(pool, uid, "email_entregue_caixa")
        await repo.atualizar_campos(redis, message_id, {"status_atual": "ENTREGUE_CAIXA"})
        return {"acao": "atualizado", "message_id": message_id, "code": code}

    if code in ("NOT_DELIVERED", "REJECTED"):
        cls = classificar_falha_email(cause=cause, description=description)
        if cls == ResultadoClassificacaoEmail.HARD_BOUNCE:
            tel = (dados.get("telefone_sms_fallback") or "").strip()
            ext = dados.get("external_id") or ""
            if not tel:
                _log.error(
                    "Hard bounce sem telefone_sms_fallback; SMS não gerado. external_id=%s",
                    ext,
                )
                await tocar_engajamento(pool, uid, "email_bounce_hard_sem_sms")
                await repo.remover(redis, message_id)
                return {
                    "acao": "bounce_sem_telefone",
                    "external_id": ext,
                    "message_id": message_id,
                }
            ctx = _contexto_sms_de_hash(dados)
            sms_ext = f"{ext}:bounce_email:{uuid.uuid4().hex[:12]}"
            sms_redis = RepositorioSmsPendenteRedis()
            uid_sms = dados.get("usuario_id") or None
            inseriu = await sms_redis.criar(
                redis,
                external_id=sms_ext,
                telefone=tel,
                tipo_template=TEMPLATE_SMS_EMAIL_INVALIDO,
                contexto=ctx,
                remetente=(dados.get("remetente") or None) or None,
                origem="bounce_email",
                usuario_id=uid_sms if uid_sms else None,
            )
            await tocar_engajamento(pool, uid, "email_bounce_hard_sms_fila")
            await repo.remover(redis, message_id)
            return {
                "acao": "bounce_sms_enfileirado" if inseriu else "bounce_sms_duplicado",
                "external_id_sms": sms_ext,
                "inseriu": inseriu,
                "message_id": message_id,
            }

        # caixa cheia / temporário / desconhecido → mantém na fila e reagenda sweep
        await tocar_engajamento(pool, uid, f"email_falha_recuperavel_{cls.value}")
        await repo.atualizar_campos(
            redis,
            message_id,
            {"status_atual": "AGUARDANDO_REENVIO", "ultimo_cause": (cause or "")[:500]},
        )
        novo_sweep = int(time.time()) + cfg.sweep_email_pendente_dias * 86400
        await repo.reagendar_sweep(redis, message_id, novo_sweep)
        return {
            "acao": "reagendado_fila",
            "classificacao": cls.value,
            "message_id": message_id,
        }

    _log.warning("Código de status e-mail não tratado: %s", code)
    return {"acao": "nao_tratado", "code": code, "message_id": message_id}

from __future__ import annotations
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
import asyncpg
from redis.asyncio import Redis
from app.config.config import Configuracao
from app.config.postgres_identificadores import obter_identificadores_postgres
from app.reenvio.api.dto.webhook_zenvia import WebhookMessageStatusZenvia
from app.mensageria.repositorios.postgres_sms_enviados import (
    atualizar_status_por_id_interno,
    buscar_por_id_mensagem_zenvia,
)
from app.reenvio.repositorios.postgres_webhook_eventos import registrar_evento_se_novo
from app.reenvio.repositorios.redis_consulta_notificacao import parse_consulta_id_hash
from app.reenvio.repositorios.redis_sms_pendente import RepositorioSmsPendenteRedis
from app.reenvio.servicos.classificar_cause_email import classificar_falha_sms_numero
from app.reenvio.servicos.cliente_stub import registrar_telefone_invalido_stub
from app.reenvio.servicos.engajamento_estado import EngajamentoSmsEstado
from app.reenvio.servicos.engajamento_fornecedor import tocar_engajamento_sms

_log = logging.getLogger(__name__)

def _contexto_de_row(row: asyncpg.Record) -> dict[str, str]:
    ctx = row["contexto"]
    if isinstance(ctx, str):
        try:
            ctx = json.loads(ctx)
        except json.JSONDecodeError:
            ctx = {}
    if not isinstance(ctx, dict):
        return {}
    return {str(k): str(v) for k, v in ctx.items() if v is not None}

async def processar_webhook_status_sms(
    pool: asyncpg.Pool,
    redis: Redis,
    cfg: Configuracao,
    payload: WebhookMessageStatusZenvia,
) -> dict[str, Any]:
    if payload.channel != "sms":
        return {"acao": "ignorado", "motivo": "canal não é sms"}

    novo = await registrar_evento_se_novo(pool, payload.id)
    if not novo:
        return {"acao": "duplicado", "id_evento": payload.id}

    row = await buscar_por_id_mensagem_zenvia(pool, payload.messageId)
    if row is None:
        _log.info(
            "Webhook SMS sem linha em sms_enviados (message_id=%s). Envio fora desta API?",
            payload.messageId,
        )
        return {"acao": "linha_nao_encontrada", "message_id": payload.messageId}

    id_interno = row["id"]
    telefone = row["telefone"]
    _cf = obter_identificadores_postgres().col_fornecedor_id
    fid: uuid.UUID | None = row[_cf]
    tentativas = int(row["tentativas_reprocessar"] or 0)
    code = payload.messageStatus.code
    cause = payload.messageStatus.cause
    description = payload.messageStatus.description
    motivo = " ".join(x for x in (cause, description) if x)[:2000] or None

    if code in ("DELIVERED", "READ"):
        await atualizar_status_por_id_interno(
            pool,
            id_interno=id_interno,
            status_ultimo="enviado",
            motivo=motivo,
        )
        await tocar_engajamento_sms(pool, fid, EngajamentoSmsEstado.SMS_ENTREGUE)
        return {"acao": "sms_enviado", "id": str(id_interno), "code": code}

    if code == "SENT":
        await atualizar_status_por_id_interno(
            pool,
            id_interno=id_interno,
            status_ultimo="processando",
            motivo=motivo,
        )
        await tocar_engajamento_sms(pool, fid, EngajamentoSmsEstado.SMS_WEBHOOK_SENT)
        return {"acao": "sms_encaminhado_provedor", "id": str(id_interno)}

    if code in ("NOT_DELIVERED", "REJECTED"):
        if classificar_falha_sms_numero(cause=cause, description=description):
            await registrar_telefone_invalido_stub(telefone=telefone, motivo=motivo)
            await atualizar_status_por_id_interno(
                pool,
                id_interno=id_interno,
                status_ultimo="falha_definitiva",
                motivo=motivo,
            )
            await tocar_engajamento_sms(pool, fid, EngajamentoSmsEstado.SMS_FALHA_NUMERO)
            return {"acao": "sms_falha_definitiva_numero", "id": str(id_interno)}

        max_t = cfg.reenvio_sms_reprocessar_max
        if tentativas >= max_t:
            await atualizar_status_por_id_interno(
                pool,
                id_interno=id_interno,
                status_ultimo="falha_definitiva",
                motivo=f"limite reprocessar ({max_t}): {motivo or ''}"[:2000],
                tentativas=tentativas,
            )
            await tocar_engajamento_sms(pool, fid, EngajamentoSmsEstado.SMS_FALHA_LIMITE)
            return {"acao": "sms_falha_limite", "id": str(id_interno)}

        proxima = datetime.now(timezone.utc) + timedelta(minutes=30)
        await atualizar_status_por_id_interno(
            pool,
            id_interno=id_interno,
            status_ultimo="reprocessar",
            motivo=motivo,
            tentativas=tentativas + 1,
            proxima_tentativa_em=proxima,
        )
        rredis = RepositorioSmsPendenteRedis()
        ctx = _contexto_de_row(row)
        cid = parse_consulta_id_hash(ctx.get("id_consulta"))
        criou = await rredis.criar(
            redis,
            id_externo=row["id_externo"],
            telefone=row["telefone"],
            tipo_template=row["tipo_template"],
            contexto=ctx,
            remetente=row["remetente"],
            origem="webhook_reprocessar",
            fornecedor_id=str(fid) if fid else None,
            consulta_id=cid,
        )
        if not criou:
            _log.warning(
                "Reprocessar: já existia pendente Redis para id_externo=%s",
                row["id_externo"],
            )
        await tocar_engajamento_sms(pool, fid, EngajamentoSmsEstado.SMS_REPROCESSAR_FILA)
        return {"acao": "sms_reprocessar", "id": str(id_interno), "tentativas": tentativas + 1}

    _log.warning("Código SMS não tratado: %s", code)
    return {"acao": "nao_tratado", "code": code, "message_id": payload.messageId}

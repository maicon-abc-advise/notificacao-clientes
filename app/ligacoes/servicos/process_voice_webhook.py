"""Processamento do webhook Vapi → atualização de ``ligacoes_enviadas``."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import asyncpg

from app.ligacoes.repositorios import postgres_ligacoes_enviadas as repo_pg
from app.reenvio.repositorios.postgres_webhook_eventos import registrar_evento_se_novo

_log = logging.getLogger(__name__)

_STATUS_VAPI_PARA_INTERNO: dict[str, str] = {
    "queued": "disparado",
    "ringing": "tocando",
    "in-progress": "em_andamento",
    "forwarding": "em_andamento",
    "ended": "concluido",
}

_MOTIVO_PARA_STATUS: dict[str, str] = {
    "customer-did-not-answer": "sem_resposta",
    "voicemail": "caixa_postal",
    "voicemail-reached": "caixa_postal",
}


def _parse_ts(val: Any) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return datetime.fromtimestamp(float(val) / 1000.0 if float(val) > 1e12 else float(val), tz=timezone.utc)
    s = str(val).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _extrair_message(payload: dict[str, Any]) -> dict[str, Any]:
    msg = payload.get("message")
    return msg if isinstance(msg, dict) else payload


def _id_evento_dedup(message: dict[str, Any]) -> str | None:
    call = message.get("call") if isinstance(message.get("call"), dict) else {}
    call_id = call.get("id") or message.get("callId")
    tipo = message.get("type") or ""
    ts = message.get("timestamp") or message.get("createdAt") or ""
    if not call_id or not tipo:
        return None
    return f"vapi:{call_id}:{tipo}:{ts}"


def _mapear_status_fim(ended_reason: str | None) -> str:
    motivo = (ended_reason or "").strip().lower()
    if motivo in _MOTIVO_PARA_STATUS:
        return _MOTIVO_PARA_STATUS[motivo]
    if motivo.startswith("pipeline-error") or motivo.startswith("pipeline-error-"):
        return "falha"
    if motivo in ("assistant-error", "twilio-failed", "vonage-failed"):
        return "falha"
    return "concluido"


def _extrair_analysis(message: dict[str, Any]) -> tuple[int | None, bool | None, dict[str, Any]]:
    analysis = message.get("analysis") or {}
    if not isinstance(analysis, dict):
        analysis = {}
    structured = analysis.get("structuredData") or analysis.get("structuredOutputs") or {}
    if not isinstance(structured, dict):
        structured = {}
    nota = structured.get("satisfaction_0_to_5")
    vai = structured.get("going_to_register")
    nota_int: int | None = None
    if nota is not None:
        try:
            nota_int = int(nota)
        except (TypeError, ValueError):
            nota_int = None
    vai_bool: bool | None = None
    if isinstance(vai, bool):
        vai_bool = vai
    elif vai is not None:
        vai_bool = str(vai).lower() in ("true", "1", "yes")
    return nota_int, vai_bool, analysis


async def processar_webhook_voz(pool: asyncpg.Pool, payload: dict[str, Any]) -> dict[str, Any]:
    message = _extrair_message(payload)
    tipo = str(message.get("type") or "")
    call = message.get("call") if isinstance(message.get("call"), dict) else {}
    id_chamada_vapi = str(call.get("id") or message.get("callId") or "")
    metadata = call.get("metadata") if isinstance(call.get("metadata"), dict) else {}
    id_externo = str(metadata.get("id_externo") or "")

    id_evento = _id_evento_dedup(message)
    if id_evento:
        if not await registrar_evento_se_novo(pool, id_evento):
            return {"ok": True, "ignorado": "duplicado"}

    registro = None
    if id_chamada_vapi:
        registro = await repo_pg.buscar_por_id_chamada_vapi(pool, id_chamada_vapi)
    if registro is None and id_externo:
        registro = await repo_pg.buscar_por_id_externo(pool, id_externo)

    if registro is None:
        _log.warning(
            "Webhook Vapi sem registro ligacoes_enviadas call=%s id_externo=%s tipo=%s",
            id_chamada_vapi,
            id_externo,
            tipo,
        )
        return {"ok": True, "ignorado": "registro_nao_encontrado"}

    reg_id = registro["id"]

    if tipo == "status-update":
        status_vapi = str(message.get("status") or call.get("status") or "").lower()
        status_ultimo = _STATUS_VAPI_PARA_INTERNO.get(status_vapi, status_vapi or "em_andamento")
        if status_ultimo in ("disparado", "tocando", "em_andamento"):
            await repo_pg.atualizar_status_intermediario(pool, registro_id=reg_id, status_ultimo=status_ultimo)
        return {"ok": True, "atualizado": "status-update", "status_ultimo": status_ultimo}

    if tipo == "end-of-call-report":
        ended_reason = str(
            message.get("endedReason")
            or call.get("endedReason")
            or message.get("endReason")
            or "",
        ) or None
        status_ultimo = _mapear_status_fim(ended_reason)
        artifact = message.get("artifact") if isinstance(message.get("artifact"), dict) else {}
        transcript = (
            message.get("transcript")
            or artifact.get("transcript")
            or call.get("transcript")
        )
        recording = (
            message.get("recordingUrl")
            or artifact.get("recordingUrl")
            or call.get("recordingUrl")
        )
        duracao = message.get("durationSeconds") or call.get("duration") or message.get("duration")
        duracao_int: int | None = None
        if duracao is not None:
            try:
                duracao_int = int(float(duracao))
            except (TypeError, ValueError):
                duracao_int = None

        iniciado = _parse_ts(call.get("startedAt") or message.get("startedAt"))
        encerrado = _parse_ts(call.get("endedAt") or message.get("endedAt"))
        nota, vai, analise = _extrair_analysis(message)

        await repo_pg.atualizar_fim_chamada(
            pool,
            registro_id=reg_id,
            status_ultimo=status_ultimo,
            motivo_encerramento=ended_reason,
            transcricao=str(transcript) if transcript else None,
            url_gravacao=str(recording) if recording else None,
            duracao_segundos=duracao_int,
            iniciado_em=iniciado,
            encerrado_em=encerrado,
            nota_satisfacao=nota,
            vai_cadastrar=vai,
            analise_json=analise,
        )
        return {"ok": True, "atualizado": "end-of-call-report", "status_ultimo": status_ultimo}

    return {"ok": True, "ignorado": f"tipo_{tipo or 'desconhecido'}"}

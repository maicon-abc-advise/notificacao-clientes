"""Agente de decisão do funil WhatsApp (heurística + OpenAI opcional)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.config.config import Configuracao
from app.whatsapp.servicos.conversation_analysis import (
    AnalyzedConversation,
    ConversationOutcome,
    analyze_conversation,
)

_log = logging.getLogger(__name__)

VALID_STEPS = frozenset({
    "concluir_sucesso",
    "concluir_falha",
    "marcar_falha_retornar_pendente",
    "aguardar_resposta",
    "enviar_resposta",
    "sem_acao",
})

_SYSTEM_PROMPT = "Analise conversa B2B WhatsApp e retorne JSON."


@dataclass
class AgentDecision:
    proximo_passo: str
    motivo: str
    mensagem_resposta: str | None = None
    outcome: ConversationOutcome = ConversationOutcome.INCONCLUSIVO
    source: str = "heuristica"
    debug: dict[str, Any] | None = None


def _format_thread(messages: list[dict]) -> str:
    thread_lines: list[str] = []
    for msg in messages:
        incoming = not (msg.get("key") or {}).get("fromMe", msg.get("fromMe", False))
        prefix = "Fornecedor" if incoming else "Cláudia"
        text = msg.get("message", {})
        if isinstance(text, dict):
            text = text.get("conversation") or text.get("extendedTextMessage", {}).get("text") or ""
        thread_lines.append(f"{prefix}: {text}")
    return "\n".join(thread_lines) or "(vazio)"


def _debug_base(messages: list[dict], ctx: dict) -> dict[str, Any]:
    source = ctx.get("conversation_source") or "desconhecida"
    debug: dict[str, Any] = {
        "telefone": ctx.get("telefone"),
        "remote_jid": ctx.get("remote_jid"),
        "conversation_source": source,
        "mensagens_total": len(messages),
        "thread": _format_thread(messages),
    }
    fetch_debug = ctx.get("conversation_fetch_debug")
    if isinstance(fetch_debug, dict):
        debug.update(fetch_debug)
    if source == "evolution" or ctx.get("redis_fallback_evolution"):
        debug["evolution_filtro"] = {"where": {"key": {"remoteJid": ctx.get("remote_jid")}}}
        debug["evolution_mensagens_total"] = len(messages)
    return debug


def _legacy_decision(analysis: AnalyzedConversation) -> AgentDecision:
    mapping = {
        ConversationOutcome.SUCESSO: "concluir_sucesso",
        ConversationOutcome.FALHA: "concluir_falha",
        ConversationOutcome.INCONCLUSIVO: "marcar_falha_retornar_pendente",
        ConversationOutcome.SEM_CONVERSA: "sem_acao",
    }
    step = mapping[analysis.outcome]
    return AgentDecision(
        proximo_passo=step,
        motivo=analysis.reason,
        mensagem_resposta=None,
        outcome=analysis.outcome,
        source="heuristica",
    )


def decide_next_step(
    messages: list[dict],
    ctx: dict,
    *,
    since: datetime | None = None,
    cfg: Configuracao | None = None,
) -> AgentDecision:
    if ctx.get("cadastrado"):
        return AgentDecision(
            proximo_passo="concluir_sucesso",
            motivo="Fornecedor já cadastrado na plataforma",
            outcome=ConversationOutcome.SUCESSO,
            source="regra",
            debug={
                "openai_nao_chamada": "fornecedor já cadastrado na plataforma",
                "evolution_mensagens_total": len(messages),
            },
        )

    debug = _debug_base(messages, ctx)
    api_key = (cfg.openai_api_key if cfg else "") or ""
    if not api_key.strip():
        analysis = analyze_conversation(messages, since=since)
        decision = _legacy_decision(analysis)
        debug["modo"] = "heuristica"
        debug["analise"] = {
            "outcome": analysis.outcome.value,
            "motivo": analysis.reason,
            "mensagens_fornecedor": analysis.incoming_count,
        }
        decision.debug = debug
        return decision

    try:
        from openai import OpenAI

        thread = debug["thread"]
        prompt = (
            f"Contexto: CNPJ {ctx.get('cnpj_basico')} status={ctx.get('status')} "
            f"cadastrado={ctx.get('cadastrado')}\nHistórico:\n{thread}\n"
            'Retorne JSON: {"proximo_passo": "...", "motivo": "...", "mensagem_resposta": null}'
        )
        model = (cfg.openai_model if cfg else "gpt-4o-mini") or "gpt-4o-mini"
        openai_request = {
            "model": model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.3,
        }
        debug["modo"] = "openai"
        debug["openai_request"] = openai_request

        client = OpenAI(api_key=api_key.strip())
        resp = client.chat.completions.create(**openai_request)
        parsed = json.loads(resp.choices[0].message.content or "{}")
        debug["openai_resposta"] = parsed

        step = str(parsed.get("proximo_passo", "sem_acao"))
        if step not in VALID_STEPS:
            step = "sem_acao"
        return AgentDecision(
            proximo_passo=step,
            motivo=str(parsed.get("motivo") or ""),
            mensagem_resposta=parsed.get("mensagem_resposta"),
            source="openai",
            debug=debug,
        )
    except Exception as exc:
        _log.warning("OpenAI indisponível, heurística: %s", exc)
        analysis = analyze_conversation(messages, since=since)
        decision = _legacy_decision(analysis)
        decision.motivo = f"{decision.motivo} (fallback: {exc})"
        debug["modo"] = "heuristica_fallback"
        debug["erro_openai"] = str(exc)
        debug["analise"] = {
            "outcome": analysis.outcome.value,
            "motivo": analysis.reason,
            "mensagens_fornecedor": analysis.incoming_count,
        }
        decision.debug = debug
        return decision

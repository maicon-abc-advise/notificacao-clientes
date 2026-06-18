"""Agente de decisão do funil WhatsApp (heurística + OpenAI opcional)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime

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


@dataclass
class AgentDecision:
    proximo_passo: str
    motivo: str
    mensagem_resposta: str | None = None
    outcome: ConversationOutcome = ConversationOutcome.INCONCLUSIVO
    source: str = "heuristica"


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
        )

    api_key = (cfg.openai_api_key if cfg else "") or ""
    if not api_key.strip():
        return _legacy_decision(analyze_conversation(messages, since=since))

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key.strip())
        thread_lines = []
        for msg in messages:
            incoming = not (msg.get("key") or {}).get("fromMe", msg.get("fromMe", False))
            prefix = "Fornecedor" if incoming else "Cláudia"
            text = msg.get("message", {})
            if isinstance(text, dict):
                text = text.get("conversation") or text.get("extendedTextMessage", {}).get("text") or ""
            thread_lines.append(f"{prefix}: {text}")
        thread = "\n".join(thread_lines) or "(vazio)"
        prompt = (
            f"Contexto: CNPJ {ctx.get('cnpj_basico')} status={ctx.get('status')} "
            f"cadastrado={ctx.get('cadastrado')}\nHistórico:\n{thread}\n"
            'Retorne JSON: {"proximo_passo": "...", "motivo": "...", "mensagem_resposta": null}'
        )
        resp = client.chat.completions.create(
            model=(cfg.openai_model if cfg else "gpt-4o-mini") or "gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Analise conversa B2B WhatsApp e retorne JSON."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        parsed = json.loads(resp.choices[0].message.content or "{}")
        step = str(parsed.get("proximo_passo", "sem_acao"))
        if step not in VALID_STEPS:
            step = "sem_acao"
        return AgentDecision(
            proximo_passo=step,
            motivo=str(parsed.get("motivo") or ""),
            mensagem_resposta=parsed.get("mensagem_resposta"),
            source="openai",
        )
    except Exception as exc:
        _log.warning("OpenAI indisponível, heurística: %s", exc)
        decision = _legacy_decision(analyze_conversation(messages, since=since))
        decision.motivo = f"{decision.motivo} (fallback: {exc})"
        return decision

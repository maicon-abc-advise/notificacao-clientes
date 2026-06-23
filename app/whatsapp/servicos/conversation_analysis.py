"""Análise heurística de conversa WhatsApp (fallback sem OpenAI)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum


class ConversationOutcome(str, Enum):
    SUCESSO = "sucesso"
    FALHA = "falha"
    IGNORADO = "ignorado"
    INCONCLUSIVO = "inconclusivo"
    SEM_CONVERSA = "sem_conversa"


@dataclass
class AnalyzedConversation:
    outcome: ConversationOutcome
    incoming_count: int
    last_incoming_at: datetime | None
    reason: str


_POSITIVE = re.compile(
    r"\b(sim|claro|pode|podemos|tenho interesse|interessad[oa]|dispon[ií]vel|"
    r"aceito|combinado|vamos|ok+|beleza|perfeito|pode enviar|manda|"
    r"sem problemas|com certeza|cadastr|criei a conta|já me cadastrei)\b",
    re.IGNORECASE,
)
_NEGATIVE = re.compile(
    r"\b(n[aã]o tenho interesse|sem interesse|pare|stop|bloque|"
    r"n[aã]o receb|n[aã]o posso|fora do segmento)\b",
    re.IGNORECASE,
)


def _extract_text(message: dict) -> str:
    msg = message.get("message") or {}
    if isinstance(msg, str):
        return msg.strip()
    for key in ("conversation", "extendedTextMessage", "imageMessage", "videoMessage"):
        block = msg.get(key)
        if isinstance(block, str):
            return block.strip()
        if isinstance(block, dict):
            text = block.get("text") or block.get("caption")
            if text:
                return str(text).strip()
    return ""


def _message_timestamp(message: dict) -> datetime | None:
    ts = message.get("messageTimestamp") or message.get("timestamp")
    if ts is None:
        return None
    try:
        value = float(ts)
    except (TypeError, ValueError):
        return None
    if value > 1_000_000_000_000:
        value /= 1000
    return datetime.fromtimestamp(value, tz=UTC)


def _is_incoming(message: dict) -> bool:
    key = message.get("key") or {}
    if "fromMe" in key:
        return not bool(key["fromMe"])
    return not bool(message.get("fromMe", False))


def analyze_conversation(
    messages: list[dict],
    *,
    since: datetime | None = None,
) -> AnalyzedConversation:
    incoming: list[tuple[datetime | None, str]] = []
    for msg in messages:
        if not _is_incoming(msg):
            continue
        ts = _message_timestamp(msg)
        if since and ts and ts <= since:
            continue
        text = _extract_text(msg)
        if text:
            incoming.append((ts, text))

    if not incoming:
        return AnalyzedConversation(
            outcome=ConversationOutcome.IGNORADO,
            incoming_count=0,
            last_incoming_at=None,
            reason="Fornecedor ignorou a proposta (sem resposta desde o último contato)",
        )

    texts = " ".join(t for _, t in incoming)
    last_ts = max((t for t, _ in incoming if t), default=None)

    if _NEGATIVE.search(texts):
        return AnalyzedConversation(
            outcome=ConversationOutcome.FALHA,
            incoming_count=len(incoming),
            last_incoming_at=last_ts,
            reason="Recusa ou pedido para parar detectado",
        )
    if _POSITIVE.search(texts):
        return AnalyzedConversation(
            outcome=ConversationOutcome.SUCESSO,
            incoming_count=len(incoming),
            last_incoming_at=last_ts,
            reason="Interesse ou confirmação detectada",
        )
    return AnalyzedConversation(
        outcome=ConversationOutcome.INCONCLUSIVO,
        incoming_count=len(incoming),
        last_incoming_at=last_ts,
        reason="Fornecedor manteve a conversa sem fechamento claro",
    )

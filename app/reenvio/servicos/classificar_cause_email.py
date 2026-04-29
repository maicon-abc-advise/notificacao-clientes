"""Classifica texto livre de ``cause``/``description`` (Zenvia) para regras de negócio."""

from __future__ import annotations

import enum


class ResultadoClassificacaoEmail(enum.StrEnum):
    """Decisão para e-mails NOT_DELIVERED / REJECTED."""
    HARD_BOUNCE = "hard_bounce"  # endereço inválido → SMS imediato
    MAILBOX_FULL = "mailbox_full"  # caixa cheia → volta à fila Redis
    TEMPORARY = "temporary"  # transitório → volta à fila
    UNKNOWN = "unknown"  # conservador: mantém na fila


def classificar_falha_email(*, cause: str | None, description: str | None) -> ResultadoClassificacaoEmail:
    blob = " ".join(x for x in (cause or "", description or "") if x).lower()

    if not blob.strip():
        return ResultadoClassificacaoEmail.UNKNOWN

    hard = (
        "invalid",
        "does not exist",
        "unknown user",
        "user unknown",
        "no such user",
        "mailbox not found",
        "550",
        "551",
        "553",
        "5.1.1",
        "5.1.0",
        "bad destination",
        "recipient rejected",
    )
    if any(k in blob for k in hard):
        return ResultadoClassificacaoEmail.HARD_BOUNCE

    full = (
        "mailbox full",
        "over quota",
        "quota exceeded",
        "452",
        "4.2.2",
        "552",
        "storage",
    )
    if any(k in blob for k in full):
        return ResultadoClassificacaoEmail.MAILBOX_FULL

    temporary = (
        "greylist",
        "try again",
        "temporar",
        "4.3.",
        "4.4.",
        "4.7.",
        "timeout",
        "connection refused",
        "421",
        "450",
    )
    if any(k in blob for k in temporary):
        return ResultadoClassificacaoEmail.TEMPORARY

    return ResultadoClassificacaoEmail.UNKNOWN


def classificar_falha_sms_numero(*, cause: str | None, description: str | None) -> bool:
    """Heurística: True se parece número/destino inválido (falha definitiva do cliente)."""
    blob = " ".join(x for x in (cause or "", description or "") if x).lower()
    if not blob:
        return False
    invalid = (
        "invalid",
        "unknown",
        "not a mobile",
        "bad number",
        "malformed",
        "rejected",
        "400",
        "invalid phone",
    )
    return any(k in blob for k in invalid)

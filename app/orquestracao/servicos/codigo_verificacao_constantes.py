"""Constantes do fluxo SMS de código de verificação."""

from __future__ import annotations

from uuid import uuid4


def id_externo_codigo_verificacao() -> str:
    return f"codigo-verificacao-{uuid4()}"

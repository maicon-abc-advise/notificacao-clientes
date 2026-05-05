from __future__ import annotations

from typing import Any


def extrair_primeiro_email_telefone(full_profile: dict[str, Any]) -> tuple[str | None, str | None]:
    contato = full_profile.get("contato")
    if not isinstance(contato, dict):
        return None, None
    email: str | None = None
    emails = contato.get("emails")
    if isinstance(emails, list):
        for x in emails:
            if isinstance(x, str) and (s := x.strip()):
                email = s
                break
    telefone: str | None = None
    telefones = contato.get("telefones")
    if isinstance(telefones, list):
        for x in telefones:
            if isinstance(x, str) and (s := x.strip()):
                telefone = s
                break
    return email, telefone

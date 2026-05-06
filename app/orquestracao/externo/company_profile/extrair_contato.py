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


def extrair_todos_emails_telefones(full_profile: dict[str, Any]) -> tuple[list[str], list[str]]:
    contato = full_profile.get("contato")
    if not isinstance(contato, dict):
        return [], []
    emails_out: list[str] = []
    emails = contato.get("emails")
    if isinstance(emails, list):
        seen: set[str] = set()
        for x in emails:
            if isinstance(x, str) and (s := x.strip().lower()) and s not in seen:
                seen.add(s)
                emails_out.append(s)
    telefones_out: list[str] = []
    telefones = contato.get("telefones")
    if isinstance(telefones, list):
        seen_t: set[str] = set()
        for x in telefones:
            if isinstance(x, str) and (s := x.strip()) and s not in seen_t:
                seen_t.add(s)
                telefones_out.append(s)
    return emails_out, telefones_out

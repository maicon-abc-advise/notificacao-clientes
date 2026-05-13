"""Extrai vários e-mails e telefones de strings únicas vindas do recebe-consulta (best-effort)."""

from __future__ import annotations

import re

from app.reenvio.servicos.engajamento_contatos import normalizar_email

_EMAIL_TOKEN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


def emails_do_payload(s: str | None) -> tuple[str, ...]:
    if not s or not (t := s.strip()):
        return ()
    seen: set[str] = set()
    out: list[str] = []
    for m in _EMAIL_TOKEN.finditer(t):
        n = normalizar_email(m.group(0))
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return tuple(out)


def _telefone_digitos_nacionais(fragmento: str) -> str:
    return re.sub(r"\D", "", fragmento)


def extrair_telefones_br_do_texto(raw: str | None) -> list[str]:
    """Best-effort: blocos ``(DD) ...`` ou, se não houver, um único bloco de dígitos."""
    if not raw or not (s := raw.strip()):
        return []
    partes = re.split(r"\(\s*(\d{2})\s*\)", s)
    if len(partes) < 3:
        d = _telefone_digitos_nacionais(s)
        return [d] if d else []
    out: list[str] = []
    i = 1
    while i + 1 < len(partes):
        dd = partes[i]
        corpo = partes[i + 1]
        d = _telefone_digitos_nacionais(dd + corpo)
        if d:
            out.append(d)
        i += 2
    return out


def garantir_prefixo_55_digitos(digitos: str) -> str:
    """Prefixo internacional 55 quando ainda não estiver presente (somente dígitos na entrada)."""
    if not digitos:
        return ""
    if digitos.startswith("55"):
        return digitos
    return "55" + digitos


def telefones_normalizados_do_payload(s: str | None) -> tuple[str, ...]:
    """Lista ordenada, deduplicada, só dígitos, sempre com prefixo ``55`` quando faltava."""
    brutos = extrair_telefones_br_do_texto(s)
    seen: set[str] = set()
    out: list[str] = []
    for b in brutos:
        com55 = garantir_prefixo_55_digitos(b)
        if not com55:
            continue
        if com55 not in seen:
            seen.add(com55)
            out.append(com55)
    return tuple(out)

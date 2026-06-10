"""Validação de telefone BR para ligações de voz (móvel ou fixo)."""

from __future__ import annotations

from app.reenvio.servicos.validacao_telefone_sms_br import (
    _ddd_plausivel,
    _somente_digitos,
    garantir_prefixo_55_digitos,
    normalizar_telefone_movel_br_para_sms,
)


def normalizar_telefone_br_para_voz(raw: str | None) -> str | None:
    """E.164 sem ``+``: ``55`` + DDD + número (móvel 11 dígitos nacionais ou fixo 10)."""
    movel = normalizar_telefone_movel_br_para_sms(raw)
    if movel:
        return movel

    d = _somente_digitos(raw)
    if not d:
        return None
    d = garantir_prefixo_55_digitos(d)
    if not d.startswith("55") or len(d) > 15:
        return None
    national = d[2:]
    if national.startswith(("0800", "0300", "0500", "4003")):
        return None
    if not _ddd_plausivel(national[:2]):
        return None
    if len(national) == 10 and national[2] in "2345":
        return d
    return None


def telefone_para_e164(raw: str | None) -> str | None:
    n = normalizar_telefone_br_para_voz(raw)
    if not n:
        return None
    return f"+{n}" if not str(raw or "").strip().startswith("+") else f"+{n}"


def validar_telefone_para_voz_br(entrada: str | None) -> bool:
    return normalizar_telefone_br_para_voz(entrada) is not None

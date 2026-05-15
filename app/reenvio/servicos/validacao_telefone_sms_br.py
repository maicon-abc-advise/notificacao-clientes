"""Validação única para destino SMS BR (móvel): orquestração e mensageria."""

from __future__ import annotations

import re

MOTIVO_FALHA_SMS_TELEFONE_INVALIDO = "FALHA POR TELEFONE INVÁLIDO"


def _somente_digitos(endereco: str | None) -> str:
    """Apenas dígitos (alinhado a ``engajamento_contatos.normalizar_telefone``)."""
    raw = (endereco or "").strip()
    if not raw:
        return ""
    return re.sub(r"\D", "", raw)

_DDD_MIN = 11
_DDD_MAX = 99


def garantir_prefixo_55_digitos(digitos: str) -> str:
    """Prefixo internacional 55 quando ainda não estiver presente (somente dígitos na entrada)."""
    if not digitos:
        return ""
    if digitos.startswith("55"):
        return digitos
    return "55" + digitos


def _ddd_plausivel(dd: str) -> bool:
    if len(dd) != 2:
        return False
    try:
        n = int(dd)
    except ValueError:
        return False
    return _DDD_MIN <= n <= _DDD_MAX


def normalizar_telefone_movel_br_para_sms(raw: str | None) -> str | None:
    """Só dígitos no formato ``55`` + DDD + ``9`` + 8 dígitos, ou ``None`` se inválido para SMS."""
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
    if len(national) == 11:
        if national[2] != "9":
            return None
        return d
    if len(national) == 10:
        third = national[2]
        if third in "2345":
            return None
        if third == "9":
            return "55" + national
        if third in "678":
            fixed_national = national[:2] + "9" + national[2:]
            if len(fixed_national) == 11 and fixed_national[2] == "9":
                return "55" + fixed_national
        return None
    return None


def validar_telefone_para_sms_br(entrada: str | None) -> bool:
    return normalizar_telefone_movel_br_para_sms(entrada) is not None


def filtrar_telefones_normalizados_validos_sms_br(com55_ordenados: list[str]) -> tuple[str, ...]:
    """Mantém ordem relativa; deduplica por número canónico móvel."""
    out: list[str] = []
    seen: set[str] = set()
    for x in com55_ordenados:
        n = normalizar_telefone_movel_br_para_sms(x)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return tuple(out)

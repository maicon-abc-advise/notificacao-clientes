"""Extrai vários e-mails e telefones de strings únicas vindas do recebe-consulta (best-effort).

Regras alinhadas a ``analise_telefone.md``: âncoras ``(DD)``, ``+55`` com espaços, blocos 0800/0300/0500/4003,
separadores fortes; evita colar todos os dígitos da string num único token.
"""

from __future__ import annotations

import re

from app.reenvio.servicos.engajamento_contatos import normalizar_email

_EMAIL_TOKEN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

# (0xx11) → (11)
_RE_0XX = re.compile(r"\(\s*0xx\s*(\d{2})\s*\)", re.I)
_RE_PARENT = re.compile(r"\(\s*(\d{2})\s*\)")
# +55 (21) 9 8765-4321 / +55 21 3876-5432; corpo pode incluir "/" antes do próximo +55; termina antes de palavra (ex.: SAC).
_RE_MAIS55 = re.compile(
    r"\+?\s*55\s*(?:\(\s*(\d{2})\s*\)\s*|(\d{2})\s+)([\d\s.\-+/]+?)(?=\s*/\s*\+?\s*55\b|\s*(?:\+?\s*55\b|\()|\s*[|;]|\s+[A-Za-zÀ-ú]{2,}\b|\s*$|$)",
    re.I,
)
_RE_MAIS55_COLADO = re.compile(r"\+55\s*(\d{2})(\d{9,11})\b")
_RE_WA_ME = re.compile(r"wa\.me/\+?(\d{10,15})\b", re.I)
# Não confundir sufixo "-0500" de fixo com serviço 0500: serviço só após início/fim de palavra "limpo".
_RE_SERVICO_COMPLETO = re.compile(
    r"(?:^|(?<=\s))(?<![0-9-])(0800|0300|0500|4003)\s*([\d\s.\-+]{3,22}?)(?=\s*(?:\(|\s+(?:0800|0300|0500|4003)\b)|\+55|\s*[|;]|\s+[A-Za-zÀ-ú]{2,}\b|$)",
    re.I,
)


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


def _dig(fragmento: str) -> str:
    return re.sub(r"\D", "", fragmento)


def _sanear_telefone_bruto(raw: str) -> str:
    s = (raw or "").replace("\u00a0", " ").strip()
    s = _RE_0XX.sub(r"(\1)", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _remover_emails(s: str) -> str:
    return _EMAIL_TOKEN.sub(" ", s)


# Em JSON com "fax", não inferir DDD sobre o valor do fax (analise_telefone.md).
_RE_JSON_FAX = re.compile(r'(?i)"fax"\s*:\s*"[^"]*"')
_RE_JSON_FAX_APOST = re.compile(r"(?i)'fax'\s*:\s*'[^']*'")


def _mascarar_fax_json(s: str) -> str:
    s = _RE_JSON_FAX.sub(lambda m: " " * len(m.group(0)), s)
    return _RE_JSON_FAX_APOST.sub(lambda m: " " * len(m.group(0)), s)


def _proximo_fim_corpo_parenteses(s: str, start: int) -> int:
    """Fim exclusivo do corpo após ``)`` de ``(DD)``: antes de outro ``(DD)`` ou serviço (não sufixo ``-0500``)."""
    sub = s[start:]
    m = re.search(r"\s+\(\s*\d{2}\s*\)|\s+(?:0800|0300|0500|4003)\b", sub)
    if not m:
        return len(s)
    return start + m.start()


def _extrair_parenteses(s: str) -> list[str]:
    out: list[str] = []
    pos = 0
    while True:
        m = _RE_PARENT.search(s, pos)
        if not m:
            break
        dd = m.group(1)
        corpo_fim = _proximo_fim_corpo_parenteses(s, m.end())
        corpo = s[m.end() : corpo_fim]
        d = _dig(corpo)
        if 8 <= len(d) <= 11:
            out.append(dd + d)
        pos = corpo_fim
    return out


def _extrair_servicos(s: str) -> list[str]:
    out: list[str] = []
    for m in _RE_SERVICO_COMPLETO.finditer(s):
        prefixo = m.group(1)
        corpo = _dig(m.group(2) or "")
        if not corpo:
            continue
        full = prefixo + corpo
        if 10 <= len(full) <= 12:
            out.append(full)
    return out


def _extrair_mais55(s: str) -> list[str]:
    out: list[str] = []
    for m in _RE_MAIS55.finditer(s):
        dd = m.group(1) or m.group(2)
        corpo = _dig(m.group(3) or "")
        if not corpo:
            continue
        if 8 <= len(corpo) <= 11:
            out.append(dd + corpo)
    for m in _RE_MAIS55_COLADO.finditer(s):
        dd = m.group(1)
        corpo = m.group(2)
        if 9 <= len(corpo) <= 11:
            out.append(dd + corpo)
    return out


def _extrair_wa_me(s: str) -> list[str]:
    out: list[str] = []
    for m in _RE_WA_ME.finditer(s):
        d = m.group(1)
        if d.startswith("55") and len(d) >= 12:
            out.append(d[2:])
        elif len(d) in (10, 11):
            out.append(d)
    return out


def _nacional_plausivel(d: str) -> bool:
    if len(d) not in (10, 11):
        return False
    try:
        dd = int(d[:2])
    except ValueError:
        return False
    if dd < 11 or dd > 99:
        return False
    if len(d) == 10:
        return True
    # 11: móvel (9 na posição 2) ou cadeias legadas de CRM sem checagem estrita
    return True


def _split_colagem_11_11(monstro: str) -> tuple[str, str] | None:
    if len(monstro) != 22:
        return None
    a, b = monstro[:11], monstro[11:]
    if _nacional_plausivel(a) and _nacional_plausivel(b):
        return a, b
    return None


_RE_DDD_MOVEL_FORMATADO = re.compile(
    r"\b(\d{2})\s+(9\d{4})\s*[-.]?\s*(\d{4})\b",
)


_RE_DDD_FIXO_TRACO = re.compile(r"\b(\d{2})\s*-\s*(\d{4})\s*-\s*(\d{4})\b")


def _extrair_ddd_formatado(s: str) -> list[str]:
    out: list[str] = []
    for m in _RE_DDD_MOVEL_FORMATADO.finditer(s):
        out.append(m.group(1) + m.group(2) + m.group(3))
    for m in _RE_DDD_FIXO_TRACO.finditer(s):
        out.append(m.group(1) + m.group(2) + m.group(3))
    return out


def _extrair_digitos_soltos(s: str) -> list[str]:
    r"""``(DD)`` ausente: trechos ``\d{10}`` / ``\d{11}`` isolados; tentativa de partir monstro 22 dígitos."""
    out: list[str] = []
    for m in re.finditer(r"(?<!\d)(\d{11})(?!\d)", s):
        w = m.group(1)
        if w.startswith(("0800", "0300", "0500", "4003")):
            continue
        if _nacional_plausivel(w):
            out.append(w)
    for m in re.finditer(r"(?<!\d)(\d{10})(?!\d)", s):
        w = m.group(1)
        if w.startswith("0800"):
            continue
        if _nacional_plausivel(w):
            out.append(w)
    for m in re.finditer(r"\d{16,}", s):
        sp = _split_colagem_11_11(m.group(0))
        if sp:
            out.extend(sp)
    return out


def extrair_telefones_br_do_texto(raw: str | None) -> list[str]:
    """Lista de números nacionais em **só dígitos** (sem prefixo 55 obrigatório; ver ``garantir_prefixo_55_digitos``)."""
    if not raw or not (s0 := raw.strip()):
        return []
    s = _sanear_telefone_bruto(_remover_emails(s0))
    s = _mascarar_fax_json(s)
    if not s.strip():
        return []

    candidatos: list[str] = []
    for parte in re.split(r"[\n|;]+", s):
        p = parte.strip()
        if not p:
            continue
        candidatos.extend(_extrair_parenteses(p))
        candidatos.extend(_extrair_mais55(p))
        candidatos.extend(_extrair_wa_me(p))
        candidatos.extend(_extrair_servicos(p))

    candidatos.extend(_extrair_parenteses(s))
    candidatos.extend(_extrair_mais55(s))
    candidatos.extend(_extrair_wa_me(s))
    candidatos.extend(_extrair_servicos(s))

    work = s
    candidatos.extend(_extrair_ddd_formatado(work))
    candidatos.extend(_extrair_digitos_soltos(work))

    out_ord: list[str] = []
    seen_d: set[str] = set()
    for c in candidatos:
        c = c.strip()
        if not c or c in seen_d:
            continue
        seen_d.add(c)
        out_ord.append(c)
    return out_ord


def garantir_prefixo_55_digitos(digitos: str) -> str:
    """Prefixo internacional 55 quando ainda não estiver presente (somente dígitos na entrada)."""
    if not digitos:
        return ""
    if digitos.startswith("55"):
        return digitos
    return "55" + digitos


def _prioridade_sms(d: str) -> tuple[int, int]:
    """Menor tupla = mais prioritário: móvel BR (11 dígitos nacionais após 55 com 9 na posição 2)."""
    if not d.startswith("55") or len(d) < 12:
        return (4, len(d))
    resto = d[2:]
    if resto.startswith(("0800", "0300", "0500", "4003")):
        return (3, len(d))
    if len(resto) == 11 and resto[2] == "9":
        return (0, len(d))
    if len(resto) == 10:
        return (1, len(d))
    return (2, len(d))


def telefones_normalizados_do_payload(s: str | None) -> tuple[str, ...]:
    """Lista deduplicada, só dígitos, prefixo ``55`` quando faltava; ordenada (móvel > fixo > serviço)."""
    brutos = extrair_telefones_br_do_texto(s)
    vistos: set[str] = set()
    com55_list: list[str] = []
    for b in brutos:
        com55 = garantir_prefixo_55_digitos(b)
        if not com55:
            continue
        if len(com55) > 15:
            continue
        if com55 not in vistos:
            vistos.add(com55)
            com55_list.append(com55)
    com55_list.sort(key=_prioridade_sms)
    return tuple(com55_list)

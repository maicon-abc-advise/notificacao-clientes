"""Sanitização de textos do e-mail de contato (HTML seguro + quebras legíveis)."""

from __future__ import annotations

import re
from html import escape

_CONTROLES = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ESPACOS = re.compile(r"[ \t\f\v]+")


def sanitizar_texto_contato(texto: str, *, permitir_quebras: bool = False) -> str:
    """Remove controles, escapa HTML; opcionalmente converte newlines em ``<br>``."""
    t = (texto or "").strip()
    t = _CONTROLES.sub("", t)
    if permitir_quebras:
        t = t.replace("\r\n", "\n").replace("\r", "\n")
        partes = [escape(_ESPACOS.sub(" ", p).strip()) for p in t.split("\n")]
        # preserva linhas vazias intencionais como <br> extra
        t = "<br>".join(partes)
        t = re.sub(r"(?:<br>){3,}", "<br><br>", t).strip()
        # remove <br> só nas pontas
        while t.startswith("<br>"):
            t = t[4:]
        while t.endswith("<br>"):
            t = t[:-4]
        return t.strip()
    t = t.replace("\r", " ").replace("\n", " ")
    t = _ESPACOS.sub(" ", t).strip()
    return escape(t)

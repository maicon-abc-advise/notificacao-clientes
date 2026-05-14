"""Literais genéricos para placeholders de template (UF / segmento)."""

from __future__ import annotations

SEGMENTO_GENERICO = "seu segmento"
UF_GENERICO = "sua região"


def contexto_para_render(contexto: dict[str, str]) -> dict[str, str]:
    """Preenche ``uf`` e ``segmento`` vazios antes do render (ex.: SMS com truncagem na orquestração)."""
    out = dict(contexto)
    u = (out.get("uf") or "").strip()
    out["uf"] = u or UF_GENERICO
    s = (out.get("segmento") or "").strip()
    out["segmento"] = s or SEGMENTO_GENERICO
    return out

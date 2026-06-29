from __future__ import annotations

VARIANTE_PADRAO = "simples"
VARIANTES_VALIDAS = frozenset({VARIANTE_PADRAO, "elaborado"})


def normalizar_variante(valor: str | None) -> str:
    v = (valor or "").strip().lower()
    if v in VARIANTES_VALIDAS:
        return v
    return VARIANTE_PADRAO

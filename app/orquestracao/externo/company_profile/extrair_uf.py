from __future__ import annotations

from typing import Any


def _texto_util(v: object) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def extrair_uf_de_company_profile(data: dict[str, Any]) -> str | None:
    """Lê UF a partir de ``full_profile`` (chaves comuns ou objeto aninhado)."""
    for key in ("uf", "estado", "sigla_uf", "state"):
        u = _texto_util(data.get(key))
        if u:
            return u
    for nested_key in ("endereco", "address", "localizacao", "location"):
        bloco = data.get(nested_key)
        if isinstance(bloco, dict):
            u = _texto_util(bloco.get("uf") or bloco.get("estado") or bloco.get("state"))
            if u:
                return u
    return None

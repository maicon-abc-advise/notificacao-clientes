from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class CatalogoIncidente:
    descricao: str
    periodo_inicio: str
    periodo_fim: str
    consulta_ids: frozenset[str]
    pares_consulta_cnpj: tuple[dict[str, str], ...]
    cnpjs_basicos: frozenset[str]

    def consulta_permitida(self, consulta_id: str | None) -> bool:
        s = (consulta_id or "").strip().lower()
        return bool(s) and s in self.consulta_ids


@lru_cache
def carregar_catalogo_incidente() -> CatalogoIncidente:
    path = Path(__file__).resolve().parent / "consultas_indevidas.json"
    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    consulta_ids = frozenset(str(x).strip().lower() for x in raw.get("consulta_ids", []) if str(x).strip())
    pares = tuple(
        {
            "consulta_id": str(p["consulta_id"]).strip().lower(),
            "cnpj_basico": str(p["cnpj_basico"]).strip(),
        }
        for p in raw.get("pares_consulta_cnpj", [])
        if p.get("consulta_id") and p.get("cnpj_basico")
    )
    cnpjs = frozenset(p["cnpj_basico"] for p in pares)
    return CatalogoIncidente(
        descricao=str(raw.get("descricao", "")),
        periodo_inicio=str(raw.get("periodo_inicio", "")),
        periodo_fim=str(raw.get("periodo_fim", "")),
        consulta_ids=consulta_ids,
        pares_consulta_cnpj=pares,
        cnpjs_basicos=cnpjs,
    )

from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from typing import Any

import asyncpg


def registo_para_json(r: asyncpg.Record) -> dict[str, Any]:
    d: dict[str, Any] = {}
    for k in r.keys():
        d[k] = _valor_json(r[k])
    return d


def _valor_json(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, int) and not isinstance(v, bool):
        # bigint / identity id
        return v
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, dict):
        return {str(k): _valor_json(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_valor_json(x) for x in v]
    if isinstance(v, str):
        s = v.strip()
        if len(s) >= 2 and s[0] in "[{" and s[-1] in "]}":
            try:
                return _valor_json(json.loads(s))
            except json.JSONDecodeError:
                pass
        return v
    return v


def decodificar_contexto_json_bruto(raw: str | None) -> dict[str, Any] | list[Any] | None:
    if not raw:
        return None
    try:
        v = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return v

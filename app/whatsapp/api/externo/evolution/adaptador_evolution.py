"""Adaptador HTTP async para Evolution API."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config.config import Configuracao

_log = logging.getLogger(__name__)
_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_label_cache: dict[str, str] | None = None


class ErroEvolutionAPI(Exception):
    def __init__(self, mensagem: str, *, status_code: int | None = None) -> None:
        super().__init__(mensagem)
        self.status_code = status_code


def _headers(cfg: Configuracao) -> dict[str, str]:
    return {"apikey": cfg.evolution_key, "Content-Type": "application/json"}


def _base(cfg: Configuracao) -> str:
    url = (cfg.evolution_url or "").strip().rstrip("/")
    if not url:
        raise ErroEvolutionAPI("EVOLUTION_URL não configurada")
    if not cfg.evolution_key:
        raise ErroEvolutionAPI("EVOLUTION_KEY não configurada")
    return url


async def _request(
    cfg: Configuracao,
    method: str,
    path: str,
    body: dict | None = None,
) -> dict | list:
    url = f"{_base(cfg)}{path}"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.request(method, url, json=body, headers=_headers(cfg))
    if resp.is_error:
        detail = resp.text[:2000]
        try:
            parsed = resp.json()
            msg = parsed.get("response", {}).get("message") or parsed.get("message") or detail
            if isinstance(msg, list):
                msg = "; ".join(str(m) for m in msg)
        except Exception:
            msg = detail or resp.reason_phrase
        raise ErroEvolutionAPI(f"Evolution API ({resp.status_code}): {msg}", status_code=resp.status_code)
    if not resp.content:
        return {}
    try:
        return resp.json()
    except Exception as e:
        raise ErroEvolutionAPI("Resposta Evolution não é JSON") from e


async def verificar_numero_whatsapp(cfg: Configuracao, number: str) -> bool:
    inst = cfg.evolution_instance
    result = await _request(
        cfg,
        "POST",
        f"/chat/whatsappNumbers/{inst}",
        {"numbers": [number]},
    )
    items = result if isinstance(result, list) else result.get("numbers", [result])
    if not items:
        raise ErroEvolutionAPI("Resposta vazia ao validar número no WhatsApp")
    item = items[0] if isinstance(items[0], dict) else {}
    return bool(item.get("exists", False))


async def enviar_texto(cfg: Configuracao, number: str, text: str) -> dict[str, Any]:
    inst = cfg.evolution_instance
    payload = {"number": number, "text": text, "linkPreview": False}
    _log.info("Evolution sendText %s chars para %s", len(text), number)
    result = await _request(cfg, "POST", f"/message/sendText/{inst}", payload)
    return result if isinstance(result, dict) else {"result": result}


def _whatsapp_jid(number: str) -> str:
    digits = "".join(ch for ch in number if ch.isdigit())
    return f"{digits}@s.whatsapp.net"


async def buscar_mensagens_chat(
    cfg: Configuracao,
    number: str,
    *,
    page: int = 1,
    offset: int = 50,
) -> list[dict]:
    inst = cfg.evolution_instance
    payload = {
        "where": {"key": {"remoteJid": _whatsapp_jid(number)}},
        "page": page,
        "offset": offset,
    }
    result = await _request(cfg, "POST", f"/chat/findMessages/{inst}", payload)
    if isinstance(result, dict):
        messages = result.get("messages")
        if isinstance(messages, dict):
            records = messages.get("records")
            if isinstance(records, list):
                return records
        records = result.get("records")
        if isinstance(records, list):
            return records
    if isinstance(result, list):
        return result
    return []


async def resolver_label_id(cfg: Configuracao, label_name: str | None = None) -> str | None:
    global _label_cache
    env_id = (cfg.evolution_label_id or "").strip()
    if env_id:
        return env_id
    name = label_name or cfg.evolution_label_name
    if _label_cache is not None and name in _label_cache:
        return _label_cache[name] or None
    inst = cfg.evolution_instance
    result = await _request(cfg, "GET", f"/label/findLabels/{inst}")
    labels = result if isinstance(result, list) else result.get("labels", []) if isinstance(result, dict) else []
    _label_cache = {str(lb.get("name", "")): str(lb.get("id", "")) for lb in labels}
    if name in _label_cache:
        return _label_cache[name] or None
    for lb_name, lb_id in _label_cache.items():
        if "fornecedor" in lb_name.lower():
            return lb_id or None
    return None


async def aplicar_label_chat(cfg: Configuracao, number: str, label_id: str) -> dict:
    inst = cfg.evolution_instance
    payload = {"number": number, "labelId": label_id, "action": "add"}
    for method in ("POST", "PUT"):
        try:
            result = await _request(cfg, method, f"/label/handleLabel/{inst}", payload)
            return result if isinstance(result, dict) else {"result": result}
        except ErroEvolutionAPI as exc:
            if exc.status_code == 404 or "404" in str(exc):
                continue
            raise
    raise ErroEvolutionAPI("Endpoint de etiquetas não disponível nesta versão da Evolution API")

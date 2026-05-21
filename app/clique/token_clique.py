"""Token assinado (HMAC) para links de clique — sem Redis nem tabela extra."""

from __future__ import annotations

import base64
import hashlib
import hmac


def _assinatura(id_externo: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), id_externo.encode("utf-8"), hashlib.sha256).hexdigest()[:16]

def gerar_token_clique(id_externo: str, secret: str) -> str:
    """Gera token URL-safe: ``base64url(id_externo + '.' + sig)``."""
    payload = f"{id_externo}.{_assinatura(id_externo, secret)}"
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")

def extrair_id_externo_do_token(token: str, secret: str) -> str | None:
    """Valida assinatura e devolve ``id_externo`` ou ``None``."""
    if not token or not secret:
        return None
    try:
        pad = "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode((token + pad).encode("ascii")).decode("utf-8")
        id_externo, sig = raw.rsplit(".", 1)
        if not id_externo:
            return None
        esperado = _assinatura(id_externo, secret)
        if hmac.compare_digest(sig, esperado):
            return id_externo
    except (ValueError, UnicodeDecodeError):
        return None
    return None

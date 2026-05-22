"""Id externo (12 chars) e token de URL (12 chars) com cifra simples via ``LINK_CLIQUE_SECRET``."""

from __future__ import annotations

import hashlib
import secrets
import string

TAMANHO_ID_EXTERNO = 12
TAMANHO_TOKEN_URL = 12

_ALFABETO = string.ascii_letters + string.digits


def gerar_id_externo() -> str:
    """Gera ``id_externo`` aleatório de 12 caracteres (A–Z, a–z, 0–9)."""
    return "".join(secrets.choice(_ALFABETO) for _ in range(TAMANHO_ID_EXTERNO))


def _indices_chave(secret: str) -> list[int]:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return [digest[i] % len(_ALFABETO) for i in range(TAMANHO_TOKEN_URL)]


def _validar_id_12(id_externo: str) -> None:
    if len(id_externo) != TAMANHO_ID_EXTERNO:
        raise ValueError(f"id_externo deve ter {TAMANHO_ID_EXTERNO} caracteres")
    for c in id_externo:
        if c not in _ALFABETO:
            raise ValueError(f"caractere inválido em id_externo: {c!r}")


def cifrar_id_para_url(id_externo: str, secret: str) -> str:
    """Cifra ``id_externo`` (12) → token de URL (12), reversível com o mesmo secret."""
    _validar_id_12(id_externo)
    if not secret:
        raise ValueError("secret vazio")
    chave = _indices_chave(secret)
    return "".join(
        _ALFABETO[(_ALFABETO.index(c) + chave[i]) % len(_ALFABETO)]
        for i, c in enumerate(id_externo)
    )


def decifrar_url_para_id(token: str, secret: str) -> str | None:
    """Decifra token de URL (12) → ``id_externo`` ou ``None`` se inválido."""
    if len(token) != TAMANHO_TOKEN_URL or not secret:
        return None
    chave = _indices_chave(secret)
    try:
        out = "".join(
            _ALFABETO[(_ALFABETO.index(c) - chave[i]) % len(_ALFABETO)]
            for i, c in enumerate(token)
        )
    except ValueError:
        return None
    if len(out) != TAMANHO_ID_EXTERNO:
        return None
    return out

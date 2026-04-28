"""Segurança mínima para webhooks: cabeçalho ``X-Webhook-Secret``.

Se ``ZENVIA_WEBHOOK_SECRET`` estiver vazio no ``.env``, a verificação é
**desligada** (útil para testes manuais com Postman em local). Em produção,
defina sempre um segredo longo e aleatório.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.config.config import Configuracao, obter_configuracao

_log = logging.getLogger(__name__)


def _segredos_iguais_seguro(a: str, b: str) -> bool:
    da = hashlib.sha256(a.encode("utf-8")).digest()
    db = hashlib.sha256(b.encode("utf-8")).digest()
    return hmac.compare_digest(da, db)


async def verificar_segredo_webhook_zenvia(
    config: Annotated[Configuracao, Depends(obter_configuracao)],
    x_webhook_secret: Annotated[str | None, Header(alias="X-Webhook-Secret")] = None,
) -> None:
    esperado = config.zenvia_webhook_secret
    if not esperado:
        _log.warning(
            "ZENVIA_WEBHOOK_SECRET vazio: webhook aceito sem autenticação (apenas desenvolvimento).",
        )
        return
    recebido = x_webhook_secret or ""
    if not _segredos_iguais_seguro(recebido, esperado):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Webhook não autorizado",
        )

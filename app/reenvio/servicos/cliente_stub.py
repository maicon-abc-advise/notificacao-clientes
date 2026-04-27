"""Camada futura: atualizar cadastro do cliente quando o telefone for inválido.

Hoje só regista em log para não bloquear o fluxo do webhook.
"""

import logging

_log = logging.getLogger(__name__)


async def registrar_telefone_invalido_stub(*, telefone: str, motivo: str | None) -> None:
    _log.warning(
        "STUB cliente: telefone inválido (persistência futura). telefone=%s motivo=%s",
        telefone,
        motivo,
    )

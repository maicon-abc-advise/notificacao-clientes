"""Uso: ``python -m popula_tabelas`` (com ``popula-tabelas`` no PYTHONPATH ou projeto instalado)."""

from __future__ import annotations

import asyncio
import sys

from app.config.config import obter_configuracao

from popula_tabelas.aplicar import aplicar_tudo


async def _async_main() -> None:
    url = obter_configuracao().database_url
    await aplicar_tudo(url)
    print("popula-tabelas: concluído (templates + reenvio + orquestração).", file=sys.stderr)


def main() -> None:
    """Entrada síncrona (console script / ``python -m popula_tabelas``)."""
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()

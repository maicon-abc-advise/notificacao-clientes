"""Um comando para DDL + seed de dev/teste.

Execute na raiz do projeto ``notificacao-clientes``::

    python popula-tabelas/run.py

Equivale a aplicar, em sequência: templates (schema + dados), reenvio e orquestração.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Permite ``import popula_tabelas`` sem instalar o pacote (pasta pai no path).
_PKG_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _PKG_ROOT.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from app.config.config import obter_configuracao
from popula_tabelas.aplicar import aplicar_tudo


async def main() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        url = obter_configuracao().database_url
    await aplicar_tudo(url)
    print("popula-tabelas: concluído (templates + reenvio + orquestração).", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())

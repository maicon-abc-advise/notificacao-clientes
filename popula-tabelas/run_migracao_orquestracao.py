"""Atualiza o schema de orquestração sem apagar dados (só migrações incrementais).

Execute na raiz de ``notificacao-clientes`` (com ``.env`` e ``API_KEY`` como no app)::

    python popula-tabelas/run_migracao_orquestracao.py

Usa ``database_url`` da configuração (``DATABASE_URL_TEST`` se ``AMBIENTE=local``, etc.).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _PKG_ROOT.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from app.config.config import obter_configuracao

from popula_tabelas.aplicar import aplicar_migracoes_orquestracao_incrementais


async def main() -> None:
    url = obter_configuracao().database_url
    await aplicar_migracoes_orquestracao_incrementais(url)
    print(
        "Migração orquestração: concluída (dados existentes preservados).",
        file=sys.stderr,
    )


if __name__ == "__main__":
    asyncio.run(main())

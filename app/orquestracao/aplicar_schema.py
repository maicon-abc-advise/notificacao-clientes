import asyncio
import os
import sys
from pathlib import Path

import asyncpg

from app.config.config import obter_configuracao

_DIR_SQL = Path(__file__).resolve().parent / "sql"


async def aplicar_schema_orquestracao(dsn: str) -> None:
    sql = (_DIR_SQL / "schema_consultas_fornecedores.sql").read_text(encoding="utf-8")
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


async def main() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        url = obter_configuracao().database_url
    await aplicar_schema_orquestracao(url)
    print("Schema orquestração (consultas/fornecedores) aplicado com sucesso.", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())

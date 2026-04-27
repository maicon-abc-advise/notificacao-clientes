import asyncio
import os
import sys

from app.config.config import obter_configuracao
from app.templates.banco import aplicar_schema_e_seed

async def main() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        url = obter_configuracao().database_url
    await aplicar_schema_e_seed(url)
    print("Schema e seed aplicados com sucesso.", file=sys.stderr)

if __name__ == "__main__":
    asyncio.run(main())

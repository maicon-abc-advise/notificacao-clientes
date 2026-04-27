from pathlib import Path

import asyncpg

from app.templates.dados_seed import linhas_seed

_DIR_SQL = Path(__file__).resolve().parent / "sql"


async def aplicar_schema(dsn: str) -> None:
    schema = (_DIR_SQL / "schema.sql").read_text(encoding="utf-8")
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(schema)
    finally:
        await conn.close()

async def aplicar_seed(dsn: str) -> None:
    sql = """
    INSERT INTO public.templates_notificacao (id, tipo, email, sms)
    VALUES ($1, $2, $3, $4)
    ON CONFLICT (tipo) DO UPDATE SET
        id = EXCLUDED.id,
        email = EXCLUDED.email,
        sms = EXCLUDED.sms
    """
    conn = await asyncpg.connect(dsn)
    try:
        for id_, tipo, email, sms in linhas_seed():
            await conn.execute(sql, id_, tipo, email, sms)
    finally:
        await conn.close()

async def aplicar_schema_e_seed(dsn: str) -> None:
    await aplicar_schema(dsn)
    await aplicar_seed(dsn)

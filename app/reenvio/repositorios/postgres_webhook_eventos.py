import asyncpg
from asyncpg.exceptions import UniqueViolationError

async def registrar_evento_se_novo(pool: asyncpg.Pool, id_evento: str) -> bool:
    try:
        await pool.execute(
            "INSERT INTO public.webhook_eventos_processados (id_evento) VALUES ($1)",
            id_evento,
        )
    except UniqueViolationError:
        return False
    return True

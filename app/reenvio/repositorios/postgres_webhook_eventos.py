import asyncpg
from asyncpg.exceptions import UniqueViolationError

from app.config.postgres_identificadores import obter_identificadores_postgres


async def registrar_evento_se_novo(pool: asyncpg.Pool, id_evento: str) -> bool:
    p = obter_identificadores_postgres()
    tw = p.qual("webhook_eventos_processados")
    try:
        await pool.execute(
            f"INSERT INTO {tw} (id_evento) VALUES ($1)",
            id_evento,
        )
    except UniqueViolationError:
        return False
    return True

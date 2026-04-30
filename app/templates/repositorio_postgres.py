import asyncpg

from app.config.postgres_identificadores import obter_identificadores_postgres
from app.templates.modelo import TemplateNotificacao
from app.templates.porta import PortaTemplates


class RepositorioTemplatesPostgres:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def obter_por_tipo(self, codigo: str) -> TemplateNotificacao | None:
        p = obter_identificadores_postgres()
        tt = p.qual("templates_notificacao")
        row = await self._pool.fetchrow(
            f"""
            SELECT id, tipo, email, sms
            FROM {tt}
            WHERE tipo = $1
            """,
            codigo,
        )
        if row is None:
            return None
        return TemplateNotificacao(
            id=row["id"],
            tipo=row["tipo"],
            email=row["email"],
            sms=row["sms"],
        )

    async def listar_todos(self) -> list[TemplateNotificacao]:
        p = obter_identificadores_postgres()
        tt = p.qual("templates_notificacao")
        rows = await self._pool.fetch(
            f"""
            SELECT id, tipo, email, sms
            FROM {tt}
            ORDER BY tipo
            """
        )
        return [
            TemplateNotificacao(
                id=r["id"],
                tipo=r["tipo"],
                email=r["email"],
                sms=r["sms"],
            )
            for r in rows
        ]


def repositorio_e_porta(pool: asyncpg.Pool) -> PortaTemplates:
    return RepositorioTemplatesPostgres(pool)

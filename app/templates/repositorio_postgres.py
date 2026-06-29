import asyncpg

from app.config.postgres_identificadores import obter_identificadores_postgres
from app.experimentos.variante_email import VARIANTE_PADRAO, normalizar_variante
from app.templates.modelo import TemplateNotificacao
from app.templates.porta import PortaTemplates


def _row_para_template(row: asyncpg.Record) -> TemplateNotificacao:
    return TemplateNotificacao(
        id=row["id"],
        tipo=row["tipo"],
        email=row["email"],
        sms=row["sms"],
        variante=normalizar_variante(row.get("variante")),
        assunto=row.get("assunto"),
    )


class RepositorioTemplatesPostgres:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def obter_por_tipo_e_variante(
        self,
        codigo: str,
        variante: str = VARIANTE_PADRAO,
    ) -> TemplateNotificacao | None:
        p = obter_identificadores_postgres()
        tt = p.qual("templates_notificacao")
        var = normalizar_variante(variante)
        row = await self._pool.fetchrow(
            f"""
            SELECT id, tipo, email, sms, variante, assunto
            FROM {tt}
            WHERE tipo = $1 AND variante = $2
            """,
            codigo,
            var,
        )
        if row is None:
            return None
        return _row_para_template(row)

    async def obter_por_tipo(self, codigo: str) -> TemplateNotificacao | None:
        return await self.obter_por_tipo_e_variante(codigo, VARIANTE_PADRAO)

    async def listar_todos(self) -> list[TemplateNotificacao]:
        p = obter_identificadores_postgres()
        tt = p.qual("templates_notificacao")
        rows = await self._pool.fetch(
            f"""
            SELECT id, tipo, email, sms, variante, assunto
            FROM {tt}
            ORDER BY tipo, variante
            """
        )
        return [_row_para_template(r) for r in rows]


def repositorio_e_porta(pool: asyncpg.Pool) -> PortaTemplates:
    return RepositorioTemplatesPostgres(pool)

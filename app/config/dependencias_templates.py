from typing import Annotated
from fastapi import Depends
from app.templates.conexao import obter_pool
from app.templates.porta import PortaTemplates
from app.templates.repositorio_postgres import RepositorioTemplatesPostgres

async def obter_porta_templates() -> PortaTemplates:
    pool = await obter_pool()
    return RepositorioTemplatesPostgres(pool)

PortaTemplatesDep = Annotated[PortaTemplates, Depends(obter_porta_templates)]

from __future__ import annotations

import asyncpg

from app.orquestracao.externo.company_profile.extrair_contato import extrair_primeiro_email_telefone
from app.orquestracao.repositorios.company_profile_repo import buscar_full_profile_por_cnpj_basico
from app.orquestracao.servicos.auxiliares.porta_enriquecimento_contato import ResultadoEnriquecimentoContato


class AdaptadorCompanyProfilePostgres:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def enriquecer_por_cnpj_basico(self, cnpj_basico: str) -> ResultadoEnriquecimentoContato:
        data = await buscar_full_profile_por_cnpj_basico(self._pool, cnpj_basico=cnpj_basico)
        if not data:
            return ResultadoEnriquecimentoContato(email=None, telefone=None)
        email, telefone = extrair_primeiro_email_telefone(data)
        return ResultadoEnriquecimentoContato(email=email, telefone=telefone)

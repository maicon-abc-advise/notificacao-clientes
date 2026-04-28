from __future__ import annotations

from app.orquestracao.servicos.auxiliares.porta_enriquecimento_contato import ResultadoEnriquecimentoContato


class AdaptadorBigDataCorpApi:
    async def enriquecer_por_cnpj(self, cnpj: str) -> ResultadoEnriquecimentoContato:
        raise NotImplementedError(
            "Big Data Corp API ainda não implementada; use USE_BIGDATACORP_MOCK=true",
        )

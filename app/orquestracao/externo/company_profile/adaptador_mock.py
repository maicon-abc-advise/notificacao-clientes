from __future__ import annotations
from app.orquestracao.servicos.auxiliares.porta_enriquecimento_contato import ResultadoEnriquecimentoContato

class AdaptadorCompanyProfileMock:
    """Sempre vazio: em dev, contato só vem do payload ou de ``usuario_fornecedor`` / auth."""

    async def enriquecer_por_cnpj_basico(self, cnpj_basico: str) -> ResultadoEnriquecimentoContato:
        _ = cnpj_basico
        return ResultadoEnriquecimentoContato(email=None, telefone=None)

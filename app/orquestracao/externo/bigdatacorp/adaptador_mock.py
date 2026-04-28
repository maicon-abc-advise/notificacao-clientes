from __future__ import annotations
from app.orquestracao.servicos.auxiliares.porta_enriquecimento_contato import ResultadoEnriquecimentoContato

_MAPA_FIXO: dict[str, tuple[str | None, str | None]] = {
    "00000000000191": ("contato@empresa-mock.com.br", "5511999887766"),
}

class AdaptadorBigDataCorpMock:
    async def enriquecer_por_cnpj(self, cnpj: str) -> ResultadoEnriquecimentoContato:
        if cnpj in _MAPA_FIXO:
            e, t = _MAPA_FIXO[cnpj]
            return ResultadoEnriquecimentoContato(email=e, telefone=t)
        return ResultadoEnriquecimentoContato(
            email=f"bdcmock+{cnpj}@example.invalid",
            telefone="5511987654321",
        )

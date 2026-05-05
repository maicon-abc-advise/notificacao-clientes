from __future__ import annotations

from app.orquestracao.servicos.auxiliares.porta_enriquecimento_contato import ResultadoEnriquecimentoContato

_MAPA_FIXO: dict[str, tuple[str | None, str | None]] = {
    "00000000": ("contato@empresa-mock.com.br", "5511999887766"),
}


class AdaptadorCompanyProfileMock:
    async def enriquecer_por_cnpj_basico(self, cnpj_basico: str) -> ResultadoEnriquecimentoContato:
        if cnpj_basico in _MAPA_FIXO:
            e, t = _MAPA_FIXO[cnpj_basico]
            return ResultadoEnriquecimentoContato(email=e, telefone=t)
        return ResultadoEnriquecimentoContato(
            email=f"company_profile_mock+{cnpj_basico}@example.invalid",
            telefone="5511987654321",
        )

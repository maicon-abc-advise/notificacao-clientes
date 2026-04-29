from __future__ import annotations

from app.orquestracao.servicos.auxiliares.porta_enriquecimento_contato import ResultadoEnriquecimentoContato


class AdaptadorBigDataCorpApi:
    """Cliente HTTP real (em construção). Recebe base URL e token do ``.env``."""

    def __init__(
        self,
        api_base_url: str | None = None,
        access_token: str | None = None,
    ) -> None:
        self._api_base_url = (api_base_url or "").strip().rstrip("/") or None
        self._access_token = (access_token or "").strip() or None

    async def enriquecer_por_cnpj(self, cnpj: str) -> ResultadoEnriquecimentoContato:
        if not self._api_base_url or not self._access_token:
            raise NotImplementedError(
                "Big Data Corp: defina BIGDATACORP_API_BASE_URL e BIGDATACORP_ACCESS_TOKEN "
                "com USE_BIGDATACORP_MOCK=false. Chamada HTTP ainda não implementada.",
            )
        raise NotImplementedError(
            "Big Data Corp: chamada HTTP (datasets / empresas) ainda não implementada; "
            "credenciais já carregadas da configuração.",
        )

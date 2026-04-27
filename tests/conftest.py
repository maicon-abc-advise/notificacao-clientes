import os

import pytest

os.environ.setdefault("API_KEY", "test-api-key-unit")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
# Token fictício: rotas de envio; credenciais ficam no conector (ZENVIA_API_TOKEN).
os.environ.setdefault("ZENVIA_API_TOKEN", "test-zenvia-token-somente-para-testes")
os.environ.setdefault("MENSAGENS_PROVEDOR_EMAIL", "zenvia")
os.environ.setdefault("MENSAGENS_PROVEDOR_SMS", "zenvia")


@pytest.fixture(autouse=True)
def _limpar_cache_configuracao() -> None:
    from app.config.config import obter_configuracao
    from app.mensageria.api.externo.zenvia.parametros import obter_parametros_zenvia

    obter_configuracao.cache_clear()
    obter_parametros_zenvia.cache_clear()
    yield
    obter_configuracao.cache_clear()
    obter_parametros_zenvia.cache_clear()

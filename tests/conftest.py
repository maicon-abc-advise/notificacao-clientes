import asyncio
import os

import pytest

os.environ.setdefault("API_KEY", "test-api-key-unit")
os.environ.setdefault("AMBIENTE", "local")
os.environ.setdefault("USE_ZENVIA_MOCK", "false")
os.environ.setdefault("MOCK_COMPANY_PROFILE_ENRIQUECIMENTO", "true")
os.environ.setdefault("REDIS_URL_TEST", "redis://localhost:6379/0")
os.environ.setdefault(
    "DATABASE_URL_TEST",
    "postgresql://notificacao:notificacao_dev@127.0.0.1:5433/notificacao",
)
os.environ.setdefault("ZENVIA_API_TOKEN", "test-zenvia-token-somente-para-testes")
os.environ.setdefault("MENSAGENS_PROVEDOR_EMAIL", "zenvia")
os.environ.setdefault("MENSAGENS_PROVEDOR_SMS", "zenvia")


@pytest.fixture(autouse=True)
def _limpar_cache_configuracao() -> None:
    from app.config.config import obter_configuracao
    from app.mensageria.api.externo.zenvia.parametros import obter_parametros_zenvia
    from app.templates.conexao import fechar_pool

    obter_configuracao.cache_clear()
    obter_parametros_zenvia.cache_clear()
    yield
    obter_configuracao.cache_clear()
    obter_parametros_zenvia.cache_clear()
    asyncio.run(fechar_pool())

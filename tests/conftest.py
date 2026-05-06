import asyncio
import os

import pytest

os.environ["API_KEY"] = "test-api-key-unit"
os.environ["AMBIENTE"] = "local"
os.environ["USE_ZENVIA_MOCK"] = "true"
os.environ["MOCK_COMPANY_PROFILE_ENRIQUECIMENTO"] = "true"
os.environ["MENSAGENS_PROVEDOR_EMAIL"] = "zenvia"
os.environ["MENSAGENS_PROVEDOR_SMS"] = "zenvia"
os.environ["ZENVIA_API_TOKEN"] = "test-zenvia-token-somente-para-testes"

os.environ["REDIS_URL_TEST"] = "redis://localhost:6379/0"
os.environ["DATABASE_URL_TEST"] = "postgresql://notificacao:notificacao_dev@127.0.0.1:5433/notificacao"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["DATABASE_URL"] = "postgresql://notificacao:notificacao_dev@127.0.0.1:5433/notificacao"

os.environ["REDIS_URL_PROD"] = ""
os.environ["DATABASE_URL_PROD"] = ""


@pytest.fixture(autouse=True)
def _limpar_cache_configuracao() -> None:
    from app.config.config import obter_configuracao
    from app.mensageria.api.externo.zenvia.parametros import obter_parametros_zenvia
    from app.templates.conexao import fechar_pool

    obter_configuracao.cache_clear()
    obter_parametros_zenvia.cache_clear()
    cfg = obter_configuracao()
    db = (cfg.database_url or "").lower()
    redis = (cfg.redis_url or "").lower()
    assert "supabase" not in db and "railway" not in db
    assert "supabase" not in redis and "railway" not in redis
    yield
    obter_configuracao.cache_clear()
    obter_parametros_zenvia.cache_clear()
    asyncio.run(fechar_pool())

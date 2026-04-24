import os

import pytest

os.environ.setdefault("API_KEY", "test-api-key-unit")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")


@pytest.fixture(autouse=True)
def _limpar_cache_configuracao() -> None:
    from app.nucleo.config import obter_configuracao

    obter_configuracao.cache_clear()
    yield
    obter_configuracao.cache_clear()

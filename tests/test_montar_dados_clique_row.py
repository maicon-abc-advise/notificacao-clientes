"""Montagem de dados JSON a partir de linha emails_enviados / sms_enviados."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.clique.servicos.registrar_clique import obter_dados_clique_de_row


def test_obter_dados_clique_de_row_email() -> None:
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value={"nome_fantasia": "Metal Sul"})
    row = {
        "contexto": {"uf": "SP", "segmento": "papel"},
        "cnpj_basico": "12345678",
    }
    dados = asyncio.run(obter_dados_clique_de_row(pool, row))
    assert dados == {"uf": "SP", "segmento": "papel", "nome_empresa": "Metal Sul"}


def test_obter_dados_clique_sem_nome_usa_padrao() -> None:
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)
    row = {"contexto": {"uf": "MG", "segmento": "ti"}, "cnpj_basico": None}
    dados = asyncio.run(obter_dados_clique_de_row(pool, row))
    assert dados["nome_empresa"] == "Sua empresa"

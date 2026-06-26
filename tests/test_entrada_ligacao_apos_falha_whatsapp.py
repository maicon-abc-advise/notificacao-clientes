import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.ligacoes.servicos.entrada_ligacao_apos_falha_whatsapp import entrada_ligacao_apos_falha_whatsapp


async def _test_enfileira_com_metadados() -> None:
    pool = MagicMock()
    pool.fetchval = AsyncMock(side_effect=[5, "Farmacia X"])
    redis = MagicMock()
    repo_criar = AsyncMock(return_value=True)

    with (
        patch(
            "app.ligacoes.servicos.entrada_ligacao_apos_falha_whatsapp._fornecedor_cadastrou",
            AsyncMock(return_value=False),
        ),
        patch(
            "app.ligacoes.servicos.entrada_ligacao_apos_falha_whatsapp._engajamento_ligacao_bloqueado",
            AsyncMock(return_value=False),
        ),
        patch(
            "app.ligacoes.servicos.entrada_ligacao_apos_falha_whatsapp._pendente_ligacao_para_cnpj",
            AsyncMock(return_value=False),
        ),
        patch(
            "app.ligacoes.servicos.entrada_ligacao_apos_falha_whatsapp._resolver_uf",
            AsyncMock(return_value="SP"),
        ),
        patch(
            "app.ligacoes.servicos.entrada_ligacao_apos_falha_whatsapp._resolver_segmento",
            AsyncMock(return_value="Farmacia"),
        ),
        patch(
            "app.ligacoes.servicos.entrada_ligacao_apos_falha_whatsapp.obter_cliente_redis",
            AsyncMock(return_value=redis),
        ),
        patch(
            "app.ligacoes.servicos.entrada_ligacao_apos_falha_whatsapp._repo.criar",
            repo_criar,
        ),
    ):
        out = await entrada_ligacao_apos_falha_whatsapp(
            pool,
            cnpj_basico="12345678",
            telefone="11999998888",
            origem="whatsapp_sem_numero_valido",
            fornecedor_id=uuid.uuid4(),
        )

    assert out["retorno"] == "ligacao_enfileirada"
    assert out["origem"] == "whatsapp_sem_numero_valido"
    repo_criar.assert_awaited_once()
    kwargs = repo_criar.await_args.kwargs
    assert kwargs["cnpj_basico"] == "12345678"
    assert kwargs["uf_buscada"] == "SP"
    assert kwargs["segmento_buscado"] == "Farmacia"
    assert kwargs["quantidade_buscas"] == 5


async def _test_ignora_cadastrado() -> None:
    pool = MagicMock()
    with patch(
        "app.ligacoes.servicos.entrada_ligacao_apos_falha_whatsapp._fornecedor_cadastrou",
        AsyncMock(return_value=True),
    ):
        out = await entrada_ligacao_apos_falha_whatsapp(
            pool,
            cnpj_basico="12345678",
            telefone="11999998888",
            origem="whatsapp_etapas_esgotadas",
        )
    assert out["retorno"] == "ligacao_ignorado_cadastrado"


def test_entrada_ligacao_apos_falha_whatsapp() -> None:
    asyncio.run(_test_enfileira_com_metadados())
    asyncio.run(_test_ignora_cadastrado())

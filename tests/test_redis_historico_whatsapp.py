"""Testes do histórico WhatsApp no Redis (n8n)."""

import asyncio
from unittest.mock import AsyncMock, patch

from app.whatsapp.repositorios.redis_historico_whatsapp import (
    append_mensagem_agente_historico_redis,
    buscar_historico_redis_n8n,
    formatar_linha_agente_historico,
    jid_historico_whatsapp,
    mesclar_raw_historico_variantes,
    ordem_cronologica_lista_n8n,
    parse_lista_redis_n8n,
)
from app.whatsapp.servicos.rotina_whatsapp import ConversationFetchResult, _fetch_conversation


def test_jid_historico_whatsapp() -> None:
    assert jid_historico_whatsapp("553592373421") == "553592373421@s.whatsapp.net"


def test_formatar_linha_agente_historico() -> None:
    assert formatar_linha_agente_historico("Oi, tudo bem?") == "Agent: Oi, tudo bem?"


def test_append_mensagem_agente_historico_redis_usa_chave_do_banco_sem_nove() -> None:
    mock_redis = AsyncMock()
    mock_redis.rpush = AsyncMock(return_value=1)

    async def _run():
        with patch(
            "app.whatsapp.repositorios.redis_historico_whatsapp.obter_cliente_redis",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            return await append_mensagem_agente_historico_redis(
                "553592373421",
                "Oi, tudo bem?\n\nVi que vocês atendem o segmento.",
            )

    key = asyncio.run(_run())
    assert key == "553592373421@s.whatsapp.net"
    mock_redis.rpush.assert_awaited_once_with(
        "553592373421@s.whatsapp.net",
        "Agent: Oi, tudo bem?\n\nVi que vocês atendem o segmento.",
    )


def test_append_mensagem_agente_historico_redis_usa_chave_do_banco_com_nove() -> None:
    mock_redis = AsyncMock()
    mock_redis.rpush = AsyncMock(return_value=1)

    async def _run():
        with patch(
            "app.whatsapp.repositorios.redis_historico_whatsapp.obter_cliente_redis",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            return await append_mensagem_agente_historico_redis("5535992373421", "mensagem inicial")

    key = asyncio.run(_run())
    assert key == "5535992373421@s.whatsapp.net"
    mock_redis.rpush.assert_awaited_once_with(
        "5535992373421@s.whatsapp.net",
        "Agent: mensagem inicial",
    )


def test_parse_lista_redis_n8n_ordem_cronologica_rpush() -> None:
    jid = "553592373421@s.whatsapp.net"
    raw = [
        "Agent: primeira mensagem",
        "sim, tenho interesse",
        "Agent: segunda mensagem",
    ]
    msgs = parse_lista_redis_n8n(raw, jid)
    assert len(msgs) == 3
    assert msgs[0]["message"]["conversation"] == "primeira mensagem"
    assert msgs[0]["key"]["fromMe"] is True
    assert msgs[1]["message"]["conversation"] == "sim, tenho interesse"
    assert msgs[1]["key"]["fromMe"] is False
    assert msgs[2]["message"]["conversation"] == "segunda mensagem"
    assert msgs[2]["key"]["fromMe"] is True


def test_parse_lista_redis_n8n_conversa_intercalada() -> None:
    """Thread intercalado Cláudia ↔ Fornecedor (ordem RPUSH / WhatsApp real)."""
    jid = "553592373421@s.whatsapp.net"
    raw = [
        "Agent: Oi, tudo bem? Vi que vocês atendem o segmento.",
        "sim, tenho interesse",
        "Agent: Ótimo! Consegue se cadastrar no portal?",
        "Me cadastrei",
        "já finalizei",
    ]
    msgs = parse_lista_redis_n8n(raw, jid)
    assert len(msgs) == 5
    assert msgs[0]["key"]["fromMe"] is True
    assert msgs[1]["key"]["fromMe"] is False
    assert msgs[2]["key"]["fromMe"] is True
    assert msgs[3]["key"]["fromMe"] is False
    assert msgs[4]["key"]["fromMe"] is False
    assert msgs[3]["message"]["conversation"] == "Me cadastrei"


def test_parse_lista_redis_n8n_prefixos_opcionais() -> None:
    jid = "5511999999999@s.whatsapp.net"
    raw = ["Agent:Oi!", "Fornecedor: olá"]
    msgs = parse_lista_redis_n8n(raw, jid)
    assert msgs[0]["message"]["conversation"] == "Oi!"
    assert msgs[0]["key"]["fromMe"] is True
    assert msgs[1]["message"]["conversation"] == "olá"
    assert msgs[1]["key"]["fromMe"] is False


def test_ordem_cronologica_lista_n8n_inverte_lpush() -> None:
    lpush = ["Agent: mais nova", "Agent: meio", "fornecedor antigo"]
    assert ordem_cronologica_lista_n8n(lpush) == [
        "fornecedor antigo",
        "Agent: meio",
        "Agent: mais nova",
    ]


def test_mesclar_raw_historico_variantes_apenas_uma_chave() -> None:
    assert mesclar_raw_historico_variantes([], ["a"]) == ["a"]
    assert mesclar_raw_historico_variantes(["a"], []) == ["a"]


def test_mesclar_raw_historico_variantes_diverge_um_vs_varios() -> None:
    inicial = ["Agent: Oi, tudo bem?"]
    resto = ["Oi, boa tarde", "Sim, estamos aceitando", "Agent: Ótimo!"]
    assert mesclar_raw_historico_variantes(inicial, resto) == inicial + resto
    assert mesclar_raw_historico_variantes(resto, inicial) == inicial + resto


def test_mesclar_raw_historico_variantes_ambas_duplicada() -> None:
    linha = ["Agent: Oi"]
    assert mesclar_raw_historico_variantes(linha, linha) == linha


def test_mesclar_raw_historico_variantes_ambas_multiplas() -> None:
    registro = ["Agent: a", "Agent: b"]
    outra = ["c", "Agent: d"]
    assert mesclar_raw_historico_variantes(registro, outra) == registro + outra


def test_buscar_historico_redis_n8n_chave_unica() -> None:
    mock_redis = AsyncMock()

    async def _lrange(key: str, start: int, end: int) -> list[str]:
        if key == "553592373421@s.whatsapp.net":
            return [
                "Agent: mensagem inicial",
                "pode enviar",
            ]
        return []

    mock_redis.lrange = AsyncMock(side_effect=_lrange)

    async def _run():
        with patch(
            "app.whatsapp.repositorios.redis_historico_whatsapp.obter_cliente_redis",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            return await buscar_historico_redis_n8n("553592373421")

    result = asyncio.run(_run())
    assert result.redis_key == "553592373421@s.whatsapp.net"
    assert result.raw_total == 2
    assert len(result.messages) == 2
    assert result.messages[0]["message"]["conversation"] == "mensagem inicial"
    assert result.messages[0]["key"]["fromMe"] is True
    assert result.messages[1]["message"]["conversation"] == "pode enviar"
    assert result.messages[1]["key"]["fromMe"] is False
    assert result.variantes_tentadas == [
        "553592373421@s.whatsapp.net",
        "5535992373421@s.whatsapp.net",
    ]
    assert mock_redis.lrange.await_count == 2


def test_buscar_historico_redis_n8n_mescla_variantes_divergentes() -> None:
    """Caso real: API na chave sem 9 (1 msg), n8n na chave com 9 (resto)."""
    mock_redis = AsyncMock()
    key_sem = "551199404152@s.whatsapp.net"
    key_com = "5511999404152@s.whatsapp.net"

    async def _lrange(key: str, start: int, end: int) -> list[str]:
        if key == key_sem:
            return ["Agent: Oi, tudo bem?\n\nVocês teriam capacidade?"]
        if key == key_com:
            # Ordem LPUSH do n8n (mais nova primeiro)
            return [
                "Agent: O cadastro é gratuito...",
                "Sim, estamos aceitando",
                "Oi, boa tarde",
            ]
        return []

    mock_redis.lrange = AsyncMock(side_effect=_lrange)

    async def _run():
        with patch(
            "app.whatsapp.repositorios.redis_historico_whatsapp.obter_cliente_redis",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            return await buscar_historico_redis_n8n("551199404152")

    result = asyncio.run(_run())
    assert result.raw_total == 4
    assert len(result.messages) == 4
    assert result.messages[0]["key"]["fromMe"] is True
    assert result.messages[1]["message"]["conversation"] == "Oi, boa tarde"
    assert result.messages[1]["key"]["fromMe"] is False
    assert result.messages[2]["message"]["conversation"] == "Sim, estamos aceitando"
    assert result.raw_por_chave == {key_sem: 1, key_com: 3}


def test_buscar_historico_redis_n8n_inverte_lpush_chave_n8n() -> None:
    """Caso 551192716560: n8n LPUSH na chave com 9."""
    mock_redis = AsyncMock()
    key_sem = "551192716560@s.whatsapp.net"
    key_com = "5511992716560@s.whatsapp.net"

    async def _lrange(key: str, start: int, end: int) -> list[str]:
        if key == key_sem:
            return [
                "Agent: Oi, tudo bem?\n\nVocês teriam capacidade para receber novos pedidos?",
            ]
        if key == key_com:
            return [
                "Agent:Para se cadastrar, é só acessar https://buscafornecedor.com.br/fornecedores",
                "Agent:Lembre-se que o cadastro no BuscaFornecedor é totalmente gratuito",
                "Agent:Boa tarde! Que bom que você confirmou.",
                "Boa tarde !!  Sim.",
            ]
        return []

    mock_redis.lrange = AsyncMock(side_effect=_lrange)

    async def _run():
        with patch(
            "app.whatsapp.repositorios.redis_historico_whatsapp.obter_cliente_redis",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            return await buscar_historico_redis_n8n("551192716560")

    result = asyncio.run(_run())
    assert result.raw_total == 5
    assert result.messages[1]["message"]["conversation"] == "Boa tarde !!  Sim."
    assert result.messages[1]["key"]["fromMe"] is False
    assert result.messages[2]["message"]["conversation"] == "Boa tarde! Que bom que você confirmou."
    assert "Para se cadastrar" in result.messages[4]["message"]["conversation"]


def test_fetch_conversation_prioriza_redis() -> None:
    from app.config.config import Configuracao

    cfg = Configuracao()
    redis_msgs = [
        {
            "key": {"fromMe": True, "remoteJid": "553592373421@s.whatsapp.net"},
            "message": {"conversation": "Olá"},
        }
    ]
    redis_result = type(
        "R",
        (),
        {
            "messages": redis_msgs,
            "debug_dict": lambda self: {
                "redis_key": "553592373421@s.whatsapp.net",
                "redis_variantes_tentadas": [
                    "553592373421@s.whatsapp.net",
                    "5535992373421@s.whatsapp.net",
                ],
                "redis_mensagens_raw": 1,
            },
        },
    )()

    async def _run() -> ConversationFetchResult:
        with patch(
            "app.whatsapp.servicos.rotina_whatsapp.buscar_historico_redis_n8n",
            new_callable=AsyncMock,
            return_value=redis_result,
        ):
            return await _fetch_conversation(cfg, "35992373421")

    fetch = asyncio.run(_run())
    assert fetch.source == "redis_n8n"
    assert fetch.messages == redis_msgs
    assert fetch.fetch_debug["redis_key"] == "553592373421@s.whatsapp.net"


def test_fetch_conversation_fallback_evolution() -> None:
    from app.config.config import Configuracao

    cfg = Configuracao()
    evo_msgs = [
        {
            "key": {"fromMe": False, "remoteJid": "553592373421@s.whatsapp.net"},
            "message": {"conversation": "resposta"},
        }
    ]
    empty_redis = type(
        "R",
        (),
        {
            "messages": [],
            "debug_dict": lambda self: {
                "redis_key": None,
                "redis_variantes_tentadas": [
                    "553592373421@s.whatsapp.net",
                    "5535992373421@s.whatsapp.net",
                ],
                "redis_mensagens_raw": 0,
            },
        },
    )()

    async def _run() -> ConversationFetchResult:
        with (
            patch(
                "app.whatsapp.servicos.rotina_whatsapp.buscar_historico_redis_n8n",
                new_callable=AsyncMock,
                return_value=empty_redis,
            ),
            patch(
                "app.whatsapp.servicos.rotina_whatsapp.buscar_mensagens_chat",
                new_callable=AsyncMock,
                return_value=evo_msgs,
            ),
        ):
            return await _fetch_conversation(cfg, "35992373421")

    fetch = asyncio.run(_run())
    assert fetch.source == "evolution"
    assert fetch.messages == evo_msgs
    assert fetch.fetch_debug["redis_fallback_evolution"] is True

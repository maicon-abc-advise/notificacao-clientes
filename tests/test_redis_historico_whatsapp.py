"""Testes do histórico WhatsApp no Redis (n8n)."""

import asyncio
from unittest.mock import AsyncMock, patch

from app.whatsapp.repositorios.redis_historico_whatsapp import (
    append_mensagem_agente_historico_redis,
    buscar_historico_redis_n8n,
    formatar_linha_agente_historico,
    jid_historico_whatsapp,
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


def test_buscar_historico_redis_n8n_chave_unica() -> None:
    mock_redis = AsyncMock()
    mock_redis.lrange = AsyncMock(
        return_value=[
            "Agent: mensagem inicial",
            "pode enviar",
        ],
    )

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
    mock_redis.lrange.assert_awaited_once_with("553592373421@s.whatsapp.net", 0, -1)


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
                "redis_variantes_tentadas": ["553592373421@s.whatsapp.net"],
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
                "redis_variantes_tentadas": ["553592373421@s.whatsapp.net"],
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

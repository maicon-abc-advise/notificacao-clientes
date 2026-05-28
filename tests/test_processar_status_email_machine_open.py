from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.reenvio.api.dto.webhook_zenvia import WebhookMessageStatusZenvia
from app.reenvio.servicos import processar_status_email as svc
from tests.teste_reenvio_dto_webhook import _payload_valido_v2


def _payload(*, machine_open: bool | None = True) -> WebhookMessageStatusZenvia:
    raw = _payload_valido_v2()
    if machine_open is None:
        raw["messageStatus"]["channelData"]["email"]["clientInfo"].pop("machineOpen", None)
    else:
        raw["messageStatus"]["channelData"]["email"]["clientInfo"]["machineOpen"] = machine_open
    return WebhookMessageStatusZenvia.model_validate(raw)


def _dados_redis() -> dict[str, str]:
    return {
        "fornecedor_id": "",
        "cnpj_basico": "12345678",
        "email_destinatario": "a@b.com",
        "id_externo": "ext-1",
    }


def _run(coro):
    return asyncio.run(coro)


@patch.object(svc, "registrar_evento_se_novo", new_callable=AsyncMock, return_value=True)
@patch.object(svc, "buscar_status_por_id_mensagem_zenvia", new_callable=AsyncMock, return_value=None)
@patch.object(svc, "atualizar_status_por_id_mensagem_zenvia", new_callable=AsyncMock)
@patch.object(svc, "tocar_engajamento_email", new_callable=AsyncMock)
def test_read_machine_open_marca_lido_maquina_sem_remover_fila(
    tocar: AsyncMock,
    atualizar: AsyncMock,
    buscar_status: AsyncMock,
    _evento: AsyncMock,
) -> None:
    redis = MagicMock()
    repo = MagicMock()
    repo.obter = AsyncMock(return_value=_dados_redis())
    repo.remover = AsyncMock()

    with patch.object(svc, "RepositorioEmailsEsperandoConfirmacaoRedis", return_value=repo):
        out = _run(
            svc.processar_webhook_status_email(
                MagicMock(),
                redis,
                MagicMock(),
                _payload(machine_open=True),
            )
        )

    assert out["acao"] == "lido_maquina"
    atualizar.assert_awaited_once()
    assert atualizar.await_args.kwargs["status_ultimo"] == "lido_maquina"
    tocar.assert_not_awaited()
    repo.remover.assert_not_awaited()


@patch.object(svc, "registrar_evento_se_novo", new_callable=AsyncMock, return_value=True)
@patch.object(svc, "buscar_status_por_id_mensagem_zenvia", new_callable=AsyncMock, return_value="lido_maquina")
@patch.object(svc, "atualizar_status_por_id_mensagem_zenvia", new_callable=AsyncMock)
@patch.object(svc, "tocar_engajamento_email", new_callable=AsyncMock)
def test_read_humano_promove_de_lido_maquina(
    tocar: AsyncMock,
    atualizar: AsyncMock,
    buscar_status: AsyncMock,
    _evento: AsyncMock,
) -> None:
    redis = MagicMock()
    repo = MagicMock()
    repo.obter = AsyncMock(return_value=_dados_redis())
    repo.remover = AsyncMock()

    with patch.object(svc, "RepositorioEmailsEsperandoConfirmacaoRedis", return_value=repo):
        out = _run(
            svc.processar_webhook_status_email(
                MagicMock(),
                redis,
                MagicMock(),
                _payload(machine_open=False),
            )
        )

    assert out["acao"] == "removido_fila"
    assert atualizar.await_args.kwargs["status_ultimo"] == "lido"
    tocar.assert_awaited_once()
    repo.remover.assert_awaited_once()


@patch.object(svc, "registrar_evento_se_novo", new_callable=AsyncMock, return_value=True)
@patch.object(svc, "buscar_status_por_id_mensagem_zenvia", new_callable=AsyncMock, return_value="lido")
def test_read_ignorado_se_ja_lido(
    buscar_status: AsyncMock,
    _evento: AsyncMock,
) -> None:
    redis = MagicMock()
    repo = MagicMock()
    repo.obter = AsyncMock(return_value=_dados_redis())

    with patch.object(svc, "RepositorioEmailsEsperandoConfirmacaoRedis", return_value=repo):
        out = _run(
            svc.processar_webhook_status_email(
                MagicMock(),
                redis,
                MagicMock(),
                _payload(machine_open=True),
            )
        )

    assert out["acao"] == "read_ignorado_estado_terminal"


def test_abertura_por_maquina_no_dto() -> None:
    assert _payload(machine_open=True).abertura_por_maquina() is True
    assert _payload(machine_open=False).abertura_por_maquina() is False
    assert _payload(machine_open=None).abertura_por_maquina() is False

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from app.orquestracao.repositorios.engajamento_consulta_repo import SnapshotEngajamentoOrquestracao
from app.reenvio.servicos.engajamento_contatos import rollup_engajamento_email
from app.reenvio.servicos.engajamento_estado import (
    EngajamentoCanalAgregado,
    EngajamentoEmailEstado,
)
from app.reenvio.servicos.engajamento_contatos import rollup_engajamento_sms
from app.reenvio.servicos.engajamento_estado import EngajamentoSmsEstado
from app.reenvio.servicos.sweep_emails_pendentes import executar_sweep_emails_pendentes
from app.reenvio.servicos.sweep_sms_esperando_confirmacao import executar_sweep_sms_esperando_confirmacao


def test_rollup_email_sweep_sem_canal_agregado_inativo() -> None:
    contatos = [
        {
            "endereco": "a@b.com",
            "estado": EngajamentoEmailEstado.EMAIL_SWEEP_SEM_CANAL.value,
        }
    ]
    assert rollup_engajamento_email(contatos, "a@b.com") == EngajamentoCanalAgregado.INATIVO


def test_sweep_encerra_sem_telefone_sem_reagendar() -> None:
    asyncio.run(_test_sweep_encerra_sem_telefone_sem_reagendar())


async def _test_sweep_encerra_sem_telefone_sem_reagendar() -> None:
    redis = AsyncMock()
    pool = AsyncMock()
    cfg = AsyncMock()
    cfg.url_plataforma_sms = "https://exemplo.br"
    cfg.url_login_sms = "https://exemplo.br/login"

    repo_e = AsyncMock()
    repo_e.listar_sweep_elegiveis = AsyncMock(return_value=["msg-1"])
    repo_e.obter = AsyncMock(
        return_value={
            "id_externo": "ext1",
            "email_destinatario": "a@b.com",
            "cnpj_basico": "12345678",
            "fornecedor_id": "",
            "consulta_id": "",
            "contexto_json": "{}",
            "remetente": "",
        }
    )
    repo_e.remover = AsyncMock()
    repo_e.reagendar_sweep = AsyncMock()

    snap = SnapshotEngajamentoOrquestracao(
        engajamento_email="ativo",
        engajamento_sms="inativo",
        contatos_email=[{"endereco": "a@b.com", "estado": "email_entregue_caixa"}],
        contatos_sms=[],
        ultimo_envio_email_endereco="a@b.com",
        ultimo_envio_sms_endereco=None,
        ultimo_lembrete_limite_semanal_em=None,
    )

    with (
        patch(
            "app.reenvio.servicos.sweep_emails_pendentes.RepositorioEmailsEsperandoConfirmacaoRedis",
            return_value=repo_e,
        ),
        patch(
            "app.reenvio.servicos.sweep_emails_pendentes.RepositorioSmsPendenteRedis",
        ),
        patch(
            "app.reenvio.servicos.sweep_emails_pendentes.carregar_por_cnpj_basico",
            AsyncMock(return_value=snap),
        ),
        patch(
            "app.reenvio.servicos.sweep_emails_pendentes.tentar_enfileirar_proximo_email_engajamento",
            AsyncMock(return_value=None),
        ),
        patch(
            "app.reenvio.servicos.sweep_emails_pendentes.tocar_engajamento_email",
            AsyncMock(),
        ) as tocar,
    ):
        out = await executar_sweep_emails_pendentes(pool, redis, cfg)

    assert out == {
        "inseridos": 0,
        "ignorados": 1,
        "processados": 1,
        "candidatos": 1,
        "limite": None,
    }
    repo_e.reagendar_sweep.assert_not_called()
    repo_e.remover.assert_awaited_once_with(redis, "msg-1")
    tocar.assert_awaited_once()
    assert tocar.await_args.args[3] == EngajamentoEmailEstado.EMAIL_SWEEP_SEM_CANAL


def test_sweep_emails_respeita_limite() -> None:
    asyncio.run(_test_sweep_emails_respeita_limite())


async def _test_sweep_emails_respeita_limite() -> None:
    redis = AsyncMock()
    pool = AsyncMock()
    cfg = AsyncMock()

    repo_e = AsyncMock()
    repo_e.listar_sweep_elegiveis = AsyncMock(return_value=["msg-1", "msg-2", "msg-3"])
    repo_e.obter = AsyncMock(return_value=None)
    repo_e.remover = AsyncMock()

    with (
        patch(
            "app.reenvio.servicos.sweep_emails_pendentes.RepositorioEmailsEsperandoConfirmacaoRedis",
            return_value=repo_e,
        ),
        patch(
            "app.reenvio.servicos.sweep_emails_pendentes.RepositorioSmsPendenteRedis",
        ),
    ):
        out = await executar_sweep_emails_pendentes(pool, redis, cfg, limite=2)

    assert out["candidatos"] == 3
    assert out["limite"] == 2
    assert out["processados"] == 2
    assert repo_e.obter.await_count == 2


def test_rollup_sms_sweep_sem_canal_agregado_inativo() -> None:
    contatos = [
        {
            "endereco": "5511999999999",
            "estado": EngajamentoSmsEstado.SMS_SWEEP_SEM_CANAL.value,
        }
    ]
    assert rollup_engajamento_sms(contatos, "5511999999999") == EngajamentoCanalAgregado.INATIVO


def test_sweep_sms_encerra_sem_telefone_sem_reagendar() -> None:
    asyncio.run(_test_sweep_sms_encerra_sem_telefone_sem_reagendar())


async def _test_sweep_sms_encerra_sem_telefone_sem_reagendar() -> None:
    redis = AsyncMock()
    pool = AsyncMock()
    cfg = AsyncMock()

    repo_esp = AsyncMock()
    repo_esp.listar_sweep_elegiveis = AsyncMock(return_value=["sms-msg-1"])
    repo_esp.obter = AsyncMock(
        return_value={
            "id_externo": "ext-sms",
            "telefone_destinatario": "5511888888888",
            "cnpj_basico": "12345678",
            "fornecedor_id": "",
            "consulta_id": "",
            "contexto_json": "{}",
            "remetente": "",
            "status_atual": "AGUARDANDO_CONFIRMACAO",
        }
    )
    repo_esp.remover = AsyncMock()
    repo_esp.reagendar_sweep = AsyncMock()

    snap = SnapshotEngajamentoOrquestracao(
        engajamento_email="inativo",
        engajamento_sms="ativo",
        contatos_email=[],
        contatos_sms=[{"endereco": "5511888888888", "estado": "sms_enviado_api"}],
        ultimo_envio_email_endereco=None,
        ultimo_envio_sms_endereco="5511888888888",
        ultimo_lembrete_limite_semanal_em=None,
    )

    with (
        patch(
            "app.reenvio.servicos.sweep_sms_esperando_confirmacao.RepositorioSmsEsperandoConfirmacaoRedis",
            return_value=repo_esp,
        ),
        patch(
            "app.reenvio.servicos.sweep_sms_esperando_confirmacao.RepositorioSmsPendenteRedis",
        ),
        patch(
            "app.reenvio.servicos.sweep_sms_esperando_confirmacao.carregar_por_cnpj_basico",
            AsyncMock(return_value=snap),
        ),
        patch(
            "app.reenvio.servicos.sweep_sms_esperando_confirmacao.tocar_engajamento_sms",
            AsyncMock(),
        ) as tocar_sms,
    ):
        out = await executar_sweep_sms_esperando_confirmacao(pool, redis, cfg)

    assert out == {"inseridos": 0, "ignorados": 1, "candidatos": 1}
    repo_esp.reagendar_sweep.assert_not_called()
    repo_esp.remover.assert_awaited_once_with(redis, "sms-msg-1")
    tocar_sms.assert_awaited_once()
    assert tocar_sms.await_args.args[3] == EngajamentoSmsEstado.SMS_SWEEP_SEM_CANAL

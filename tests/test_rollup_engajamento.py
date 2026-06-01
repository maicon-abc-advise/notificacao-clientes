from __future__ import annotations

from app.reenvio.servicos.engajamento_contatos import (
    rollup_engajamento_email,
    rollup_engajamento_sms,
)
from app.reenvio.servicos.engajamento_estado import (
    EngajamentoCanalAgregado,
    EngajamentoEmailEstado,
    EngajamentoSmsEstado,
)


def _contato_email(endereco: str, estado: str) -> dict:
    return {"endereco": endereco, "estado": estado, "ultima_atualizacao_em": "2026-01-01T00:00:00Z"}


def _contato_sms(endereco: str, estado: str) -> dict:
    return {"endereco": endereco, "estado": estado, "ultima_atualizacao_em": "2026-01-01T00:00:00Z"}


def test_rollup_email_sweep_proximo_email_em_analise() -> None:
    contatos = [_contato_email("a@b.com", EngajamentoEmailEstado.EMAIL_SWEEP_PROXIMO_EMAIL.value)]
    assert (
        rollup_engajamento_email(contatos, "a@b.com")
        == EngajamentoCanalAgregado.EM_ANALISE
    )


def test_rollup_email_sweep_lembrete_sms_inativo() -> None:
    contatos = [_contato_email("a@b.com", EngajamentoEmailEstado.EMAIL_SWEEP_LEMBRETE_SMS.value)]
    assert rollup_engajamento_email(contatos, "a@b.com") == EngajamentoCanalAgregado.INATIVO


def test_rollup_email_todos_bloqueados_inativo() -> None:
    contatos = [
        _contato_email("a@b.com", EngajamentoEmailEstado.EMAIL_NAO_EXISTE.value),
        _contato_email("b@b.com", EngajamentoEmailEstado.EMAIL_SWEEP_LEMBRETE_SMS.value),
    ]
    assert rollup_engajamento_email(contatos, "b@b.com") == EngajamentoCanalAgregado.INATIVO


def test_rollup_email_bounce_com_outro_disponivel_em_analise() -> None:
    contatos = [
        _contato_email("a@b.com", EngajamentoEmailEstado.EMAIL_NAO_EXISTE.value),
        _contato_email("b@b.com", EngajamentoEmailEstado.ATIVO.value),
    ]
    assert rollup_engajamento_email(contatos, "a@b.com") == EngajamentoCanalAgregado.EM_ANALISE


def test_rollup_email_entregue_ativo() -> None:
    contatos = [_contato_email("a@b.com", EngajamentoEmailEstado.EMAIL_ENTREGUE_CAIXA.value)]
    assert rollup_engajamento_email(contatos, "a@b.com") == EngajamentoCanalAgregado.ATIVO


def test_rollup_sms_sem_telefone_disponivel_inativo() -> None:
    contatos = [
        _contato_sms("5511999999999", EngajamentoSmsEstado.SMS_NAO_EXISTE.value),
        _contato_sms("5511888888888", EngajamentoSmsEstado.SMS_NUMERO_INVALIDO.value),
    ]
    assert rollup_engajamento_sms(contatos, "5511999999999") == EngajamentoCanalAgregado.INATIVO


def test_rollup_sms_falha_com_outro_disponivel_em_analise() -> None:
    contatos = [
        _contato_sms("5511999999999", EngajamentoSmsEstado.SMS_FALHA_NUMERO.value),
        _contato_sms("5511888888888", EngajamentoSmsEstado.ATIVO.value),
    ]
    assert rollup_engajamento_sms(contatos, "5511999999999") == EngajamentoCanalAgregado.EM_ANALISE


def test_rollup_sms_enviado_api_em_analise() -> None:
    contatos = [_contato_sms("5511999999999", EngajamentoSmsEstado.SMS_ENVIADO_API.value)]
    assert rollup_engajamento_sms(contatos, "5511999999999") == EngajamentoCanalAgregado.EM_ANALISE

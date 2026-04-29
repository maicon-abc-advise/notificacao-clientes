"""Regras puras de canal para notificação de busca (sem cadência por último envio)."""

from app.orquestracao.servicos.auxiliares.decidir_canal_e_cadencia import decidir_canal_e_cadencia
from app.reenvio.servicos.engajamento_estado import EngajamentoEmailEstado, EngajamentoSmsEstado
from app.templates.modelo import CodigoTipoTemplate


def test_email_tem_prioridade() -> None:
    d = decidir_canal_e_cadencia(
        email_efetivo="a@b.com",
        telefone_efetivo="5511999999999",
        recebe_email=True,
        engajamento_email=EngajamentoEmailEstado.ATIVO.value,
        engajamento_sms=EngajamentoSmsEstado.ATIVO.value,
    )
    assert d.canal == "email"
    assert d.tipo_template == CodigoTipoTemplate.APARECEU_BUSCA


def test_bounce_hard_vai_para_sms() -> None:
    d = decidir_canal_e_cadencia(
        email_efetivo="a@b.com",
        telefone_efetivo="5511999999999",
        recebe_email=True,
        engajamento_email=EngajamentoEmailEstado.EMAIL_BOUNCE_HARD_SEM_SMS.value,
        engajamento_sms=EngajamentoSmsEstado.ATIVO.value,
    )
    assert d.canal == "sms"
    assert d.tipo_template == CodigoTipoTemplate.CONSULTADO_SEM_EMAIL


def test_sem_contato() -> None:
    d = decidir_canal_e_cadencia(
        email_efetivo=None,
        telefone_efetivo=None,
        recebe_email=True,
        engajamento_email=EngajamentoEmailEstado.ATIVO.value,
        engajamento_sms=EngajamentoSmsEstado.ATIVO.value,
    )
    assert d.canal == "nenhum"

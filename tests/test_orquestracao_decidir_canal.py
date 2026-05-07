"""Regras puras de canal para notificação de busca (sem cadência por último envio)."""

from app.orquestracao.servicos.auxiliares.decidir_canal_e_cadencia import decidir_canal_e_cadencia
from app.reenvio.servicos.engajamento_estado import EngajamentoEmailEstado, EngajamentoSmsEstado
from app.templates.modelo import CodigoTipoTemplate


def _agg_ok() -> tuple[str, str]:
    from app.reenvio.servicos.engajamento_estado import EngajamentoCanalAgregado

    return EngajamentoCanalAgregado.ATIVO.value, EngajamentoCanalAgregado.ATIVO.value


def test_email_tem_prioridade() -> None:
    ae, asms = _agg_ok()
    d = decidir_canal_e_cadencia(
        engajamento_email_agg=ae,
        engajamento_sms_agg=asms,
        email_efetivo="a@b.com",
        telefone_efetivo="5511999999999",
        estado_granular_email=EngajamentoEmailEstado.ATIVO.value,
        estado_granular_sms=EngajamentoSmsEstado.ATIVO.value,
    )
    assert d.canal == "email"
    assert d.tipo_template == CodigoTipoTemplate.APARECEU_BUSCA


def test_email_sem_usuario_fornecedor_usa_template_sem_registro() -> None:
    ae, asms = _agg_ok()
    d = decidir_canal_e_cadencia(
        engajamento_email_agg=ae,
        engajamento_sms_agg=asms,
        email_efetivo="a@b.com",
        telefone_efetivo="5511999999999",
        estado_granular_email=EngajamentoEmailEstado.ATIVO.value,
        estado_granular_sms=EngajamentoSmsEstado.ATIVO.value,
        usuario_fornecedor_cadastrado=False,
    )
    assert d.canal == "email"
    assert d.tipo_template == CodigoTipoTemplate.APARECEU_BUSCA_SEM_REGISTRO


def test_bounce_hard_vai_para_sms() -> None:
    ae, asms = _agg_ok()
    d = decidir_canal_e_cadencia(
        engajamento_email_agg=ae,
        engajamento_sms_agg=asms,
        email_efetivo="a@b.com",
        telefone_efetivo="5511999999999",
        estado_granular_email=EngajamentoEmailEstado.EMAIL_BOUNCE_HARD_SEM_SMS.value,
        estado_granular_sms=EngajamentoSmsEstado.ATIVO.value,
    )
    assert d.canal == "sms"
    assert d.tipo_template == CodigoTipoTemplate.CONSULTADO_SEM_EMAIL


def test_bounce_hard_sem_usuario_fornecedor_sms_sem_registro() -> None:
    ae, asms = _agg_ok()
    d = decidir_canal_e_cadencia(
        engajamento_email_agg=ae,
        engajamento_sms_agg=asms,
        email_efetivo="a@b.com",
        telefone_efetivo="5511999999999",
        estado_granular_email=EngajamentoEmailEstado.EMAIL_BOUNCE_HARD_SEM_SMS.value,
        estado_granular_sms=EngajamentoSmsEstado.ATIVO.value,
        usuario_fornecedor_cadastrado=False,
    )
    assert d.canal == "sms"
    assert d.tipo_template == CodigoTipoTemplate.APARECEU_BUSCA_SEM_REGISTRO


def test_sem_contato() -> None:
    ae, asms = _agg_ok()
    d = decidir_canal_e_cadencia(
        engajamento_email_agg=ae,
        engajamento_sms_agg=asms,
        email_efetivo=None,
        telefone_efetivo=None,
        estado_granular_email=EngajamentoEmailEstado.ATIVO.value,
        estado_granular_sms=EngajamentoSmsEstado.ATIVO.value,
    )
    assert d.canal == "nenhum"


def test_email_formato_invalido_vai_para_sms() -> None:
    ae, asms = _agg_ok()
    d = decidir_canal_e_cadencia(
        engajamento_email_agg=ae,
        engajamento_sms_agg=asms,
        email_efetivo="nao-e-um-email",
        telefone_efetivo="5511999999999",
        estado_granular_email=EngajamentoEmailEstado.ATIVO.value,
        estado_granular_sms=EngajamentoSmsEstado.ATIVO.value,
    )
    assert d.canal == "sms"
    assert d.tipo_template == CodigoTipoTemplate.CONSULTADO_SEM_EMAIL

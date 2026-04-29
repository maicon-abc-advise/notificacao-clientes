from __future__ import annotations

from dataclasses import dataclass

from app.reenvio.servicos.engajamento_estado import EngajamentoEmailEstado, EngajamentoSmsEstado
from app.templates.modelo import CodigoTipoTemplate


@dataclass(frozen=True, slots=True)
class DecisaoCanal:
    canal: str  # "nenhum" | "email" | "sms"
    tipo_template: CodigoTipoTemplate | None
    motivo: str


def _bounce_hard_email(engajamento_email: str) -> bool:
    return engajamento_email in (
        EngajamentoEmailEstado.EMAIL_BOUNCE_HARD_SEM_SMS.value,
        EngajamentoEmailEstado.EMAIL_BOUNCE_HARD_SMS_FILA.value,
    )


def _sms_problematico(engajamento_sms: str) -> bool:
    return engajamento_sms in (
        EngajamentoSmsEstado.SMS_FALHA_NUMERO.value,
        EngajamentoSmsEstado.SMS_FALHA_LIMITE.value,
    )


def decidir_canal_e_cadencia(
    *,
    email_efetivo: str | None,
    telefone_efetivo: str | None,
    recebe_email: bool,
    engajamento_email: str,
    engajamento_sms: str,
) -> DecisaoCanal:
    """Canal para notificação de “apareceu busca”. Cadência por dias **não** entra aqui — só em `verificar_creditos_servico`."""
    if not telefone_efetivo and not email_efetivo:
        return DecisaoCanal("nenhum", None, "sem e-mail e sem telefone após enriquecimento")

    email_ok = bool(email_efetivo) and recebe_email and not _bounce_hard_email(engajamento_email)

    if email_ok:
        return DecisaoCanal("email", CodigoTipoTemplate.APARECEU_BUSCA, "e-mail disponível e permitido")

    if telefone_efetivo and not _sms_problematico(engajamento_sms):
        if bool(email_efetivo) and not recebe_email:
            motivo_sms = "SMS: existe e-mail mas recebe_email=false em engajamento_usuarios (opt-out)"
        elif bool(email_efetivo) and _bounce_hard_email(engajamento_email):
            motivo_sms = "SMS: bounce hard de e-mail — não reenviar por e-mail"
        elif not email_efetivo:
            motivo_sms = "SMS: sem e-mail após enriquecimento"
        else:
            motivo_sms = "SMS: e-mail não utilizável para este envio"
        return DecisaoCanal("sms", CodigoTipoTemplate.CONSULTADO_SEM_EMAIL, motivo_sms)

    return DecisaoCanal("nenhum", None, "sem canal utilizável (SMS bloqueado ou sem telefone)")

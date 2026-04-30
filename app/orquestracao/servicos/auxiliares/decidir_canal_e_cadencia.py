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


def _email_formato_plausivel(email: str) -> bool:
    e = email.strip()
    if "@" not in e or e.startswith("@") or e.endswith("@"):
        return False
    local, sep, domain = e.partition("@")
    if sep != "@" or not local or not domain or "." not in domain:
        return False
    return True


def email_usavel_para_notificacao(
    email: str | None,
    *,
    recebe_email: bool,
    engajamento_email: str,
) -> bool:
    """E-mail não vazio, formato mínimo plausível, opt-in e sem bounce hard."""
    e = (email or "").strip()
    if not e or not recebe_email or _bounce_hard_email(engajamento_email):
        return False
    return _email_formato_plausivel(e)


def telefone_usavel_para_sms(telefone: str | None, engajamento_sms: str) -> bool:
    """Telefone não vazio e SMS não bloqueado por falha definitiva."""
    t = (telefone or "").strip()
    return bool(t) and not _sms_problematico(engajamento_sms)


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

    email_ok = email_usavel_para_notificacao(
        email_efetivo, recebe_email=recebe_email, engajamento_email=engajamento_email
    )

    if email_ok:
        return DecisaoCanal("email", CodigoTipoTemplate.APARECEU_BUSCA, "e-mail disponível e permitido")

    if telefone_efetivo and not _sms_problematico(engajamento_sms):
        if bool(email_efetivo) and not recebe_email:
            motivo_sms = "SMS: existe e-mail mas recebe_email=false em engajamento_fornecedores (opt-out)"
        elif bool(email_efetivo) and _bounce_hard_email(engajamento_email):
            motivo_sms = "SMS: bounce hard de e-mail — não reenviar por e-mail"
        elif not email_efetivo:
            motivo_sms = "SMS: sem e-mail após enriquecimento"
        else:
            motivo_sms = "SMS: e-mail não utilizável para este envio"
        return DecisaoCanal("sms", CodigoTipoTemplate.CONSULTADO_SEM_EMAIL, motivo_sms)

    return DecisaoCanal("nenhum", None, "sem canal utilizável (SMS bloqueado ou sem telefone)")

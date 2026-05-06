from __future__ import annotations

from dataclasses import dataclass

from app.reenvio.servicos.engajamento_contatos import (
    agregado_canal_bloqueado,
    email_granular_bloqueia_notificacao,
    sms_granular_bloqueia_notificacao,
)
from app.templates.modelo import CodigoTipoTemplate


@dataclass(frozen=True, slots=True)
class DecisaoCanal:
    canal: str  # "nenhum" | "email" | "sms"
    tipo_template: CodigoTipoTemplate | None
    motivo: str


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
    estado_granular: str,
) -> bool:
    """E-mail não vazio, formato mínimo plausível e estado granular permite envio."""
    e = (email or "").strip()
    if not e or email_granular_bloqueia_notificacao(estado_granular):
        return False
    return _email_formato_plausivel(e)


def telefone_usavel_para_sms(telefone: str | None, estado_granular: str) -> bool:
    """Telefone não vazio e estado granular SMS permite envio."""
    t = (telefone or "").strip()
    return bool(t) and not sms_granular_bloqueia_notificacao(estado_granular)


def decidir_canal_e_cadencia(
    *,
    engajamento_email_agg: str,
    engajamento_sms_agg: str,
    email_efetivo: str | None,
    telefone_efetivo: str | None,
    estado_granular_email: str,
    estado_granular_sms: str,
) -> DecisaoCanal:
    """Canal para notificação de “apareceu busca”. Cadência por dias **não** entra aqui — só em `verificar_creditos_servico`."""
    if not telefone_efetivo and not email_efetivo:
        return DecisaoCanal("nenhum", None, "sem e-mail e sem telefone após enriquecimento")

    email_ok = email_usavel_para_notificacao(
        email_efetivo,
        estado_granular=estado_granular_email,
    ) and not agregado_canal_bloqueado(engajamento_email_agg)

    if email_ok:
        return DecisaoCanal("email", CodigoTipoTemplate.APARECEU_BUSCA, "e-mail disponível e permitido")

    if (
        telefone_efetivo
        and not sms_granular_bloqueia_notificacao(estado_granular_sms)
        and not agregado_canal_bloqueado(engajamento_sms_agg)
    ):
        if not email_efetivo:
            motivo_sms = "SMS: sem e-mail após enriquecimento"
        elif email_granular_bloqueia_notificacao(estado_granular_email):
            motivo_sms = "SMS: e-mail bloqueado ou pendente — usar SMS"
        elif agregado_canal_bloqueado(engajamento_email_agg):
            motivo_sms = "SMS: engajamento e-mail inativo — usar SMS"
        else:
            motivo_sms = "SMS: e-mail não utilizável para este envio"
        return DecisaoCanal("sms", CodigoTipoTemplate.CONSULTADO_SEM_EMAIL, motivo_sms)

    if telefone_efetivo and agregado_canal_bloqueado(engajamento_sms_agg):
        return DecisaoCanal("nenhum", None, "SMS agregado inativo")
    if email_efetivo and agregado_canal_bloqueado(engajamento_email_agg) and not telefone_efetivo:
        return DecisaoCanal("nenhum", None, "e-mail agregado inativo e sem telefone")

    return DecisaoCanal("nenhum", None, "sem canal utilizável (SMS bloqueado ou sem telefone)")

from __future__ import annotations
import uuid
from app.config.config import obter_configuracao
from app.mensageria.api.dto.modelos import PedidoEnvioEmail, PedidoEnvioSms
from app.orquestracao.api.dto.recebe_consulta_dto import RecebeConsultaCorpo
from app.templates.modelo import CodigoTipoTemplate


def _saudacao_nome_ola(corpo: RecebeConsultaCorpo) -> str:
    """Nome para templates `Olá, {{ saudacao_nome }}.` (e-mail de busca)."""
    n = (corpo.nome_fantasia or "").strip()
    return n if n else "fornecedor"


def _saudacao_creditos_ola(nome: str | None) -> str:
    n = (nome or "").strip()
    return n if n else "fornecedor"


def _cfg():
    return obter_configuracao()


def contexto_email_apareceu_busca_logado(
    corpo: RecebeConsultaCorpo,
    *,
    uf: str,
    segmento: str,
) -> dict[str, str]:
    cfg = _cfg()
    return {
        "saudacao_nome": _saudacao_nome_ola(corpo),
        "uf": uf,
        "segmento": segmento,
        "url_plataforma": cfg.url_plataforma_email,
        "url_login": cfg.url_login_email,
    }


def contexto_email_apareceu_busca_sem_registro(
    corpo: RecebeConsultaCorpo,
    *,
    uf: str,
    segmento: str,
) -> dict[str, str]:
    cfg = _cfg()
    return {
        "saudacao_nome": _saudacao_nome_ola(corpo),
        "uf": uf,
        "segmento": segmento,
        "url_plataforma": cfg.url_plataforma_email,
        "url_login": cfg.url_login_email,
    }


def contexto_sms_busca(*, uf: str, segmento: str) -> dict[str, str]:
    cfg = _cfg()
    return {
        "uf": uf,
        "segmento": segmento,
        "url_plataforma": cfg.url_plataforma_sms,
        "url_login": cfg.url_login_sms,
    }


_TIPOS_EMAIL_BUSCA = frozenset(
    {CodigoTipoTemplate.APARECEU_BUSCA, CodigoTipoTemplate.APARECEU_BUSCA_SEM_REGISTRO}
)


def montar_pedido_email_apareceu_busca(
    corpo: RecebeConsultaCorpo,
    *,
    destinatario: str,
    fornecedor_id: uuid.UUID | None,
    cnpj_basico: str | None,
    id_externo: str,
    tipo_template: CodigoTipoTemplate = CodigoTipoTemplate.APARECEU_BUSCA,
    uf: str,
    segmento: str,
) -> PedidoEnvioEmail:
    if tipo_template not in _TIPOS_EMAIL_BUSCA:
        raise ValueError(f"tipo_template de e-mail inválido para busca: {tipo_template!r}")
    if tipo_template == CodigoTipoTemplate.APARECEU_BUSCA_SEM_REGISTRO:
        ctx = contexto_email_apareceu_busca_sem_registro(corpo, uf=uf, segmento=segmento)
    else:
        ctx = contexto_email_apareceu_busca_logado(corpo, uf=uf, segmento=segmento)
    return PedidoEnvioEmail(
        destinatario=destinatario,
        tipo_template=tipo_template,
        contexto=ctx,
        id_externo=id_externo,
        fornecedor_id=fornecedor_id,
        cnpj_basico=cnpj_basico,
        consulta_id=corpo.id_consulta,
    )


_TIPOS_SMS_BUSCA = frozenset(
    {CodigoTipoTemplate.CONSULTADO_SEM_EMAIL, CodigoTipoTemplate.APARECEU_BUSCA_SEM_REGISTRO}
)


def montar_pedido_sms_consultado_sem_email(
    corpo: RecebeConsultaCorpo,
    *,
    destinatario: str,
    fornecedor_id: uuid.UUID | None,
    cnpj_basico: str | None,
    id_externo: str,
    tipo_template: CodigoTipoTemplate = CodigoTipoTemplate.CONSULTADO_SEM_EMAIL,
    uf: str,
    segmento: str,
) -> PedidoEnvioSms:
    if tipo_template not in _TIPOS_SMS_BUSCA:
        raise ValueError(f"tipo_template de SMS inválido para busca: {tipo_template!r}")
    return PedidoEnvioSms(
        destinatario=destinatario,
        tipo_template=tipo_template,
        contexto=contexto_sms_busca(uf=uf, segmento=segmento),
        id_externo=id_externo,
        fornecedor_id=fornecedor_id,
        cnpj_basico=cnpj_basico,
        consulta_id=corpo.id_consulta,
    )


def contexto_email_creditos(nome: str | None, url_login: str) -> dict[str, str]:
    cfg = _cfg()
    return {
        "saudacao_nome": _saudacao_creditos_ola(nome),
        "url_plataforma": cfg.url_plataforma_email,
        "url_login": url_login,
    }


def contexto_sms_creditos(url_login: str) -> dict[str, str]:
    cfg = _cfg()
    return {
        "url_plataforma": cfg.url_plataforma_sms,
        "url_login": url_login,
    }


def montar_pedido_email_creditos_no_fim(
    *,
    destinatario: str,
    fornecedor_id: uuid.UUID,
    cnpj_basico: str,
    id_externo: str,
    nome_fantasia: str | None,
    url_login: str,
) -> PedidoEnvioEmail:
    return PedidoEnvioEmail(
        destinatario=destinatario,
        tipo_template=CodigoTipoTemplate.CREDITOS_NO_FIM,
        contexto=contexto_email_creditos(nome_fantasia, url_login),
        id_externo=id_externo,
        fornecedor_id=fornecedor_id,
        cnpj_basico=cnpj_basico,
    )


def montar_pedido_email_creditos_esgotados(
    *,
    destinatario: str,
    fornecedor_id: uuid.UUID,
    cnpj_basico: str,
    id_externo: str,
    nome_fantasia: str | None,
    url_login: str,
) -> PedidoEnvioEmail:
    return PedidoEnvioEmail(
        destinatario=destinatario,
        tipo_template=CodigoTipoTemplate.LEMBRETE_CREDITOS_ESGOTADOS,
        contexto=contexto_email_creditos(nome_fantasia, url_login),
        id_externo=id_externo,
        fornecedor_id=fornecedor_id,
        cnpj_basico=cnpj_basico,
    )


def montar_pedido_sms_creditos_no_fim(
    *,
    destinatario: str,
    fornecedor_id: uuid.UUID,
    cnpj_basico: str,
    id_externo: str,
    nome_fantasia: str | None,
    url_login: str,
) -> PedidoEnvioSms:
    return PedidoEnvioSms(
        destinatario=destinatario,
        tipo_template=CodigoTipoTemplate.CREDITOS_NO_FIM,
        contexto=contexto_sms_creditos(url_login),
        id_externo=id_externo,
        fornecedor_id=fornecedor_id,
        cnpj_basico=cnpj_basico,
        consulta_id=None,
    )


def montar_pedido_sms_creditos_esgotados(
    *,
    destinatario: str,
    fornecedor_id: uuid.UUID,
    cnpj_basico: str,
    id_externo: str,
    nome_fantasia: str | None,
    url_login: str,
) -> PedidoEnvioSms:
    return PedidoEnvioSms(
        destinatario=destinatario,
        tipo_template=CodigoTipoTemplate.LEMBRETE_CREDITOS_ESGOTADOS,
        contexto=contexto_sms_creditos(url_login),
        id_externo=id_externo,
        fornecedor_id=fornecedor_id,
        cnpj_basico=cnpj_basico,
        consulta_id=None,
    )

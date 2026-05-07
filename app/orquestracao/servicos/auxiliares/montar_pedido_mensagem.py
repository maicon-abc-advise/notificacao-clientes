from __future__ import annotations

import uuid

from app.mensageria.api.dto.modelos import PedidoEnvioEmail, PedidoEnvioSms
from app.orquestracao.api.dto.recebe_consulta_dto import RecebeConsultaCorpo
from app.templates.modelo import CodigoTipoTemplate

_URL_PLATAFORMA = "https://buscafornecedor.com.br"
_LINK_CONTA = f"{_URL_PLATAFORMA}/conta"
_LINK_CADASTRO = f"{_URL_PLATAFORMA}/cadastro"


def _saudacao_nome_ola(corpo: RecebeConsultaCorpo) -> str:
    """Nome para templates `Olá, {{ saudacao_nome }}.` (e-mail de busca)."""
    n = (corpo.nome_fantasia or "").strip()
    return n if n else "fornecedor"


def _saudacao_creditos_ola(nome: str | None) -> str:
    n = (nome or "").strip()
    return n if n else "fornecedor"


def contexto_email_apareceu_busca_logado(
    corpo: RecebeConsultaCorpo,
    *,
    uf: str,
    segmento: str,
) -> dict[str, str]:
    return {
        "saudacao_nome": _saudacao_nome_ola(corpo),
        "uf": uf,
        "segmento": segmento,
        "link_area_conta": _LINK_CONTA,
        "url_plataforma": _URL_PLATAFORMA,
    }


def contexto_email_apareceu_busca_sem_registro(
    corpo: RecebeConsultaCorpo,
    *,
    uf: str,
    segmento: str,
) -> dict[str, str]:
    return {
        "saudacao_nome": _saudacao_nome_ola(corpo),
        "uf": uf,
        "segmento": segmento,
        "link_cadastro": _LINK_CADASTRO,
        "url_plataforma": _URL_PLATAFORMA,
    }


def contexto_sms_busca(*, uf: str, segmento: str) -> dict[str, str]:
    return {
        "uf": uf,
        "segmento": segmento,
        "url_plataforma": _URL_PLATAFORMA,
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


def contexto_email_creditos(nome: str | None, link: str) -> dict[str, str]:
    return {
        "saudacao_nome": _saudacao_creditos_ola(nome),
        "link_area_creditos": link,
        "url_plataforma": _URL_PLATAFORMA,
    }


def montar_pedido_email_creditos_no_fim(
    *,
    destinatario: str,
    fornecedor_id: uuid.UUID,
    cnpj_basico: str,
    id_externo: str,
    nome_fantasia: str | None,
    link_creditos: str,
) -> PedidoEnvioEmail:
    return PedidoEnvioEmail(
        destinatario=destinatario,
        tipo_template=CodigoTipoTemplate.CREDITOS_NO_FIM,
        contexto=contexto_email_creditos(nome_fantasia, link_creditos),
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
    link_creditos: str,
) -> PedidoEnvioEmail:
    return PedidoEnvioEmail(
        destinatario=destinatario,
        tipo_template=CodigoTipoTemplate.LEMBRETE_CREDITOS_ESGOTADOS,
        contexto=contexto_email_creditos(nome_fantasia, link_creditos),
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
    link_creditos: str,
) -> PedidoEnvioSms:
    return PedidoEnvioSms(
        destinatario=destinatario,
        tipo_template=CodigoTipoTemplate.CREDITOS_NO_FIM,
        contexto={},
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
    link_creditos: str,
) -> PedidoEnvioSms:
    return PedidoEnvioSms(
        destinatario=destinatario,
        tipo_template=CodigoTipoTemplate.LEMBRETE_CREDITOS_ESGOTADOS,
        contexto={},
        id_externo=id_externo,
        fornecedor_id=fornecedor_id,
        cnpj_basico=cnpj_basico,
        consulta_id=None,
    )

from __future__ import annotations

import uuid

from app.mensageria.api.dto.modelos import PedidoEnvioEmail, PedidoEnvioSms
from app.orquestracao.api.dto.recebe_consulta_dto import RecebeConsultaCorpo
from app.templates.modelo import CodigoTipoTemplate

_URL_PLATAFORMA = "https://buscafornecedor.com.br"
_LINK_CONTA = f"{_URL_PLATAFORMA}/conta"
_LINK_CADASTRO = f"{_URL_PLATAFORMA}/cadastro"
_UNSUB = f"{_URL_PLATAFORMA}/prefs/email"


def _saudacao_busca(corpo: RecebeConsultaCorpo) -> str:
    nome = (corpo.nome_fantasia or "").strip()
    return f" {nome}," if nome else ","


def _saudacao_creditos_ola(nome: str | None) -> str:
    n = (nome or "").strip()
    return n if n else "fornecedor"


def contexto_apareceu_busca(
    corpo: RecebeConsultaCorpo,
    *,
    uf: str,
    segmento: str,
) -> dict[str, str]:
    return {
        "saudacao_nome": _saudacao_busca(corpo),
        "uf": uf,
        "segmento": segmento,
        "link_area_conta": _LINK_CONTA,
        "link_cadastro": _LINK_CADASTRO,
        "url_plataforma": _URL_PLATAFORMA,
        "url_unsubscribe": _UNSUB,
        "cnpj_basico": corpo.cnpj_basico,
        "cnpj_ordem": corpo.cnpj_ordem,
        "cnpj_dv": corpo.cnpj_dv,
        "id_consulta": str(corpo.id_consulta),
    }


def contexto_consultado_sem_email(
    corpo: RecebeConsultaCorpo,
    *,
    uf: str,
    segmento: str,
) -> dict[str, str]:
    return {
        "url_plataforma": _URL_PLATAFORMA,
        "link_area_conta": _LINK_CONTA,
        "link_cadastro": _LINK_CADASTRO,
        "uf": uf,
        "segmento": segmento,
        "cnpj_basico": corpo.cnpj_basico,
        "cnpj_ordem": corpo.cnpj_ordem,
        "cnpj_dv": corpo.cnpj_dv,
        "id_consulta": str(corpo.id_consulta),
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
    return PedidoEnvioEmail(
        destinatario=destinatario,
        tipo_template=tipo_template,
        contexto=contexto_apareceu_busca(corpo, uf=uf, segmento=segmento),
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
    ctx = (
        contexto_apareceu_busca(corpo, uf=uf, segmento=segmento)
        if tipo_template == CodigoTipoTemplate.APARECEU_BUSCA_SEM_REGISTRO
        else contexto_consultado_sem_email(corpo, uf=uf, segmento=segmento)
    )
    return PedidoEnvioSms(
        destinatario=destinatario,
        tipo_template=tipo_template,
        contexto=ctx,
        id_externo=id_externo,
        fornecedor_id=fornecedor_id,
        cnpj_basico=cnpj_basico,
        consulta_id=corpo.id_consulta,
    )


def contexto_creditos_no_fim(
    nome: str | None,
    link: str,
    cnpj_basico: str,
    *,
    cnpj_ordem: str = "",
    cnpj_dv: str = "",
) -> dict[str, str]:
    nf = nome or "Fornecedor"
    return {
        "saudacao_nome": _saudacao_creditos_ola(nome),
        "nome_fantasia": nf,
        "link_area_creditos": link,
        "cnpj_basico": cnpj_basico,
        "cnpj_ordem": cnpj_ordem,
        "cnpj_dv": cnpj_dv,
        "url_plataforma": _URL_PLATAFORMA,
        "url_unsubscribe": _UNSUB,
    }


def contexto_creditos_esgotados(
    nome: str | None,
    link: str,
    cnpj_basico: str,
    *,
    cnpj_ordem: str = "",
    cnpj_dv: str = "",
) -> dict[str, str]:
    nf = nome or "Fornecedor"
    return {
        "saudacao_nome": _saudacao_creditos_ola(nome),
        "nome_fantasia": nf,
        "link_area_creditos": link,
        "cnpj_basico": cnpj_basico,
        "cnpj_ordem": cnpj_ordem,
        "cnpj_dv": cnpj_dv,
        "url_plataforma": _URL_PLATAFORMA,
        "url_unsubscribe": _UNSUB,
    }


def montar_pedido_email_creditos_no_fim(
    *,
    destinatario: str,
    fornecedor_id: uuid.UUID,
    cnpj_basico: str,
    id_externo: str,
    nome_fantasia: str | None,
    link_creditos: str,
    cnpj_ordem: str = "",
    cnpj_dv: str = "",
) -> PedidoEnvioEmail:
    return PedidoEnvioEmail(
        destinatario=destinatario,
        tipo_template=CodigoTipoTemplate.CREDITOS_NO_FIM,
        contexto=contexto_creditos_no_fim(
            nome_fantasia,
            link_creditos,
            cnpj_basico,
            cnpj_ordem=cnpj_ordem,
            cnpj_dv=cnpj_dv,
        ),
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
    cnpj_ordem: str = "",
    cnpj_dv: str = "",
) -> PedidoEnvioEmail:
    return PedidoEnvioEmail(
        destinatario=destinatario,
        tipo_template=CodigoTipoTemplate.LEMBRETE_CREDITOS_ESGOTADOS,
        contexto=contexto_creditos_esgotados(
            nome_fantasia,
            link_creditos,
            cnpj_basico,
            cnpj_ordem=cnpj_ordem,
            cnpj_dv=cnpj_dv,
        ),
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
    cnpj_ordem: str = "",
    cnpj_dv: str = "",
) -> PedidoEnvioSms:
    return PedidoEnvioSms(
        destinatario=destinatario,
        tipo_template=CodigoTipoTemplate.CREDITOS_NO_FIM,
        contexto=contexto_creditos_no_fim(
            nome_fantasia,
            link_creditos,
            cnpj_basico,
            cnpj_ordem=cnpj_ordem,
            cnpj_dv=cnpj_dv,
        ),
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
    cnpj_ordem: str = "",
    cnpj_dv: str = "",
) -> PedidoEnvioSms:
    return PedidoEnvioSms(
        destinatario=destinatario,
        tipo_template=CodigoTipoTemplate.LEMBRETE_CREDITOS_ESGOTADOS,
        contexto=contexto_creditos_esgotados(
            nome_fantasia,
            link_creditos,
            cnpj_basico,
            cnpj_ordem=cnpj_ordem,
            cnpj_dv=cnpj_dv,
        ),
        id_externo=id_externo,
        fornecedor_id=fornecedor_id,
        cnpj_basico=cnpj_basico,
        consulta_id=None,
    )

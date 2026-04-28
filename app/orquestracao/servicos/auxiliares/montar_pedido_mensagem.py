from __future__ import annotations

import uuid

from app.mensageria.api.dto.modelos import PedidoEnvioEmail, PedidoEnvioSms
from app.orquestracao.api.dto.recebe_consulta_dto import RecebeConsultaCorpo
from app.templates.modelo import CodigoTipoTemplate


def contexto_apareceu_busca(corpo: RecebeConsultaCorpo) -> dict[str, str]:
    nome = (corpo.nome_fantasia or "").strip()
    saudacao = f" {nome}," if nome else ","
    return {
        "saudacao_nome": saudacao,
        "link_area_conta": "https://buscafornecedor.com.br/conta",
        "url_plataforma": "https://buscafornecedor.com.br",
        "url_unsubscribe": "https://buscafornecedor.com.br/prefs/email",
        "cnpj_basico": corpo.cnpj_basico,
        "cnpj_ordem": corpo.cnpj_ordem,
        "cnpj_dv": corpo.cnpj_dv,
        "id_consulta": str(corpo.id_consulta),
        "motivo": corpo.motivo or "",
    }


def contexto_consultado_sem_email(corpo: RecebeConsultaCorpo) -> dict[str, str]:
    return {
        "url_plataforma": "https://buscafornecedor.com.br",
        "link_area_conta": "https://buscafornecedor.com.br/conta",
        "id_consulta": str(corpo.id_consulta),
    }


def montar_pedido_email_apareceu_busca(
    corpo: RecebeConsultaCorpo,
    *,
    destinatario: str,
    usuario_id: uuid.UUID | None,
    id_externo: str,
    telefone_sms_fallback: str | None,
) -> PedidoEnvioEmail:
    return PedidoEnvioEmail(
        destinatario=destinatario,
        tipo_template=CodigoTipoTemplate.APARECEU_BUSCA,
        contexto=contexto_apareceu_busca(corpo),
        id_externo=id_externo,
        telefone_sms_fallback=telefone_sms_fallback,
        usuario_id=usuario_id,
        consulta_id=corpo.id_consulta,
    )


def montar_pedido_sms_consultado_sem_email(
    corpo: RecebeConsultaCorpo,
    *,
    destinatario: str,
    usuario_id: uuid.UUID | None,
    id_externo: str,
) -> PedidoEnvioSms:
    return PedidoEnvioSms(
        destinatario=destinatario,
        tipo_template=CodigoTipoTemplate.CONSULTADO_SEM_EMAIL,
        contexto=contexto_consultado_sem_email(corpo),
        id_externo=id_externo,
        usuario_id=usuario_id,
        consulta_id=corpo.id_consulta,
    )


def contexto_creditos_no_fim(nome: str | None, link: str) -> dict[str, str]:
    return {
        "nome_fantasia": nome or "Fornecedor",
        "link_area_creditos": link,
    }


def contexto_creditos_esgotados(nome: str | None, link: str) -> dict[str, str]:
    return {
        "nome_fantasia": nome or "Fornecedor",
        "link_area_creditos": link,
    }


def montar_pedido_email_creditos_no_fim(
    *,
    destinatario: str,
    usuario_id: uuid.UUID,
    id_externo: str,
    nome_fantasia: str | None,
    link_creditos: str,
) -> PedidoEnvioEmail:
    return PedidoEnvioEmail(
        destinatario=destinatario,
        tipo_template=CodigoTipoTemplate.CREDITOS_NO_FIM,
        contexto=contexto_creditos_no_fim(nome_fantasia, link_creditos),
        id_externo=id_externo,
        usuario_id=usuario_id,
    )


def montar_pedido_email_creditos_esgotados(
    *,
    destinatario: str,
    usuario_id: uuid.UUID,
    id_externo: str,
    nome_fantasia: str | None,
    link_creditos: str,
) -> PedidoEnvioEmail:
    return PedidoEnvioEmail(
        destinatario=destinatario,
        tipo_template=CodigoTipoTemplate.LEMBRETE_CREDITOS_ESGOTADOS,
        contexto=contexto_creditos_esgotados(nome_fantasia, link_creditos),
        id_externo=id_externo,
        usuario_id=usuario_id,
    )

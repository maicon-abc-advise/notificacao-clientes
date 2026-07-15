"""Envio direto de e-mail de contato comprador → fornecedor (sem fila Redis / bounce)."""

from __future__ import annotations

import logging
import uuid

import asyncpg
from fastapi import HTTPException, status

from app.mensageria.api.dto.modelos import PedidoEnvioEmail
from app.mensageria.excecoes.erro import ErroEnvioZenvia
from app.mensageria.repositorios.postgres_emails_enviados import (
    buscar_por_id_externo as buscar_email_por_id_externo,
)
from app.mensageria.servicos.executar_envio_mensagem import (
    id_provedor_valido_para_idempotencia,
    validar_engajamento_antes_envio_email,
)
from app.mensageria.servicos.materializar import materializar_email
from app.mensageria.servicos.porta import PortaEnvioMensagem
from app.mensageria.servicos.registrar_email_enviado import registrar_email_enviado_apos_sucesso
from app.orquestracao.api.dto.fornecedor_contato_dto import (
    PedidoEmailFornecedorContato,
    RespostaEmailFornecedorContato,
)
from app.orquestracao.repositorios.consultas_repo import buscar_por_id as buscar_consulta_por_id
from app.orquestracao.repositorios.engajamento_consulta_repo import garantir_linha_engajamento
from app.orquestracao.repositorios.fornecedores_repo import (
    buscar_usuario_fornecedor_por_cnpj_basico,
)
from app.orquestracao.servicos.auxiliares.enriquecer_contato_fornecedor import (
    enriquecer_retorno_completo,
)
from app.orquestracao.servicos.auxiliares.fragmentar_contatos_recebe_consulta import (
    emails_do_payload,
)
from app.orquestracao.servicos.auxiliares.montar_pedido_mensagem import (
    url_login_rastreado_para_id,
)
from app.orquestracao.servicos.auxiliares.porta_enriquecimento_contato import (
    PortaEnriquecimentoContato,
)
from app.orquestracao.servicos.fornecedor_contato_constantes import id_externo_fornecedor_contato
from app.reenvio.servicos.engajamento_contatos import agora_iso, contatos_iniciais_email
from app.reenvio.servicos.engajamento_estado import EngajamentoEmailEstado
from app.reenvio.servicos.engajamento_fornecedor import (
    persistir_contatos_iniciais_engajamento,
    tocar_engajamento_email,
)
from app.templates.modelo import CodigoTipoTemplate
from app.templates.porta import PortaTemplates

_log = logging.getLogger(__name__)

_DETALHE_SEM_EMAIL = "e-mail do fornecedor não encontrado"


async def executar_envio_email_fornecedor_contato(
    pool: asyncpg.Pool,
    porta_enriquecimento: PortaEnriquecimentoContato,
    corpo: PedidoEmailFornecedorContato,
    *,
    porta: PortaEnvioMensagem,
    templates: PortaTemplates,
) -> RespostaEmailFornecedorContato:
    await buscar_consulta_por_id(pool, corpo.consulta_id)

    id_externo = id_externo_fornecedor_contato(corpo.consulta_id, corpo.cnpj_basico)
    existente = await buscar_email_por_id_externo(pool, id_externo)
    zid = existente["id_mensagem_zenvia"] if existente else None
    if id_provedor_valido_para_idempotencia(zid):
        return RespostaEmailFornecedorContato(
            id_externo=id_externo,
            id_provedor=str(zid),
            tipo_template=str(existente["tipo_template"]),
            destinatario=str(existente["email_destinatario"]),
            status_ultimo=str(existente["status_ultimo"] or "processando"),
            idempotente=True,
        )

    fid: uuid.UUID | None = None
    email_f = (corpo.email or "").strip() or None
    try:
        row_f = await buscar_usuario_fornecedor_por_cnpj_basico(
            pool,
            cnpj_basico=corpo.cnpj_basico,
        )
        fid = row_f["fornecedor_id"]
        email_f = email_f or ((row_f["email"] or "").strip() or None)
    except LookupError:
        _log.info(
            "[orquestracao] fornecedor-contato: usuario_fornecedor ausente cnpj_basico=%s",
            corpo.cnpj_basico,
        )

    await garantir_linha_engajamento(
        pool,
        cnpj_basico=corpo.cnpj_basico,
        cnpj=None,
        fornecedor_id=fid,
        nome_fantasia=None,
    )

    r = await enriquecer_retorno_completo(
        porta_enriquecimento,
        cnpj_basico=corpo.cnpj_basico,
        emails_payload=emails_do_payload(email_f),
        telefones_payload=(),
    )
    if not r.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_DETALHE_SEM_EMAIL,
        )

    now_iso = agora_iso()
    await persistir_contatos_iniciais_engajamento(
        pool,
        cnpj_basico=corpo.cnpj_basico,
        fornecedor_id=fid,
        contatos_email=contatos_iniciais_email(list(r.emails), now_iso=now_iso),
        contatos_sms=[],
    )

    tipo = (
        CodigoTipoTemplate.CONTATO_FORNECEDOR_CADASTRADO
        if fid is not None
        else CodigoTipoTemplate.CONTATO_FORNECEDOR_SEM_CADASTRO
    )
    contexto = {
        "nome": corpo.nome.strip(),
        "mensagem": corpo.mensagem.strip(),
        "url_login": url_login_rastreado_para_id(id_externo),
    }
    pedido = PedidoEnvioEmail(
        destinatario=r.email,
        tipo_template=tipo,
        contexto=contexto,
        id_externo=id_externo,
        fornecedor_id=fid,
        cnpj_basico=corpo.cnpj_basico,
        consulta_id=corpo.consulta_id,
    )

    try:
        await validar_engajamento_antes_envio_email(pool, pedido)
        materializado = await materializar_email(pedido, templates)
        resultado = porta.enviar_email(materializado)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except ErroEnvioZenvia as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e)[:2000],
        ) from e

    msg_id = resultado.id_provedor
    if not id_provedor_valido_para_idempotencia(msg_id):
        _log.warning(
            "E-mail contato fornecedor sem id Zenvia; não gravado. id_externo=%s dest=%s",
            id_externo,
            r.email,
        )
        return RespostaEmailFornecedorContato(
            id_externo=id_externo,
            id_provedor=msg_id or "",
            tipo_template=tipo.value,
            destinatario=r.email,
            status_ultimo="processando",
            idempotente=False,
        )

    await registrar_email_enviado_apos_sucesso(
        pool,
        pedido,
        resultado,
        cnpj_basico_resolvido=corpo.cnpj_basico,
    )
    await tocar_engajamento_email(
        pool,
        fid,
        corpo.cnpj_basico,
        EngajamentoEmailEstado.EMAIL_ENVIADO_API,
        endereco=r.email,
        somente_endereco_existente=True,
    )

    return RespostaEmailFornecedorContato(
        id_externo=id_externo,
        id_provedor=msg_id,
        tipo_template=tipo.value,
        destinatario=r.email,
        status_ultimo="processando",
        idempotente=False,
    )

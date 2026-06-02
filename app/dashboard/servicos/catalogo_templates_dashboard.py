"""Catálogo de templates e campos de contexto para criação manual no dashboard."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import HTTPException, status

from app.orquestracao.servicos.auxiliares.montar_pedido_mensagem import (
    contexto_email_apareceu_busca_logado,
    contexto_email_apareceu_busca_sem_registro,
    contexto_email_creditos,
    contexto_sms_busca,
    contexto_sms_creditos,
    url_login_rastreado_para_id,
)
from app.orquestracao.api.dto.recebe_consulta_dto import RecebeConsultaCorpo
from app.templates.modelo import CodigoTipoTemplate, TemplateNotificacao

CanalDashboard = Literal["email", "sms"]

_CAMPO_NOME = {
    "chave": "nome_fantasia",
    "rotulo": "Nome fantasia",
    "tipo": "texto",
    "obrigatorio": False,
}
_CAMPO_UF = {"chave": "uf", "rotulo": "UF", "tipo": "texto", "obrigatorio": True}
_CAMPO_SEGMENTO = {"chave": "segmento", "rotulo": "Segmento", "tipo": "texto", "obrigatorio": True}

_CAMPOS_BUSCA = [_CAMPO_NOME, _CAMPO_UF, _CAMPO_SEGMENTO]
_CAMPOS_CREDITOS = [_CAMPO_NOME]
_CAMPOS_APRESENTACAO = [_CAMPO_NOME]

_SCHEMA_POR_TIPO: dict[CodigoTipoTemplate, list[dict[str, Any]]] = {
    CodigoTipoTemplate.APARECEU_BUSCA: _CAMPOS_BUSCA,
    CodigoTipoTemplate.APARECEU_BUSCA_SEM_REGISTRO: _CAMPOS_BUSCA,
    CodigoTipoTemplate.CONSULTADO_SEM_EMAIL: _CAMPOS_BUSCA,
    CodigoTipoTemplate.CREDITOS_NO_FIM: _CAMPOS_CREDITOS,
    CodigoTipoTemplate.LEMBRETE_CREDITOS_ESGOTADOS: _CAMPOS_CREDITOS,
    CodigoTipoTemplate.APRESENTACAO: _CAMPOS_APRESENTACAO,
}

_GERADOS_SERVIDOR = ("url_login", "url_plataforma", "link_plataforma", "saudacao_nome")


def _saudacao(nome_fantasia: str | None) -> str:
    n = (nome_fantasia or "").strip()
    return n if n else "fornecedor"


def _corpo_minimo(cnpj_basico: str, nome_fantasia: str | None) -> RecebeConsultaCorpo:
    return RecebeConsultaCorpo(
        id_consulta=uuid.UUID(int=0),
        cnpj_basico=cnpj_basico,
        nome_fantasia=nome_fantasia,
    )


def campos_contexto_para_tipo(tipo: CodigoTipoTemplate) -> list[dict[str, Any]]:
    return list(_SCHEMA_POR_TIPO.get(tipo, []))


def validar_campos_formulario(
    tipo: CodigoTipoTemplate,
    *,
    nome_fantasia: str | None,
    uf: str | None,
    segmento: str | None,
) -> None:
    for campo in campos_contexto_para_tipo(tipo):
        if not campo.get("obrigatorio"):
            continue
        chave = str(campo["chave"])
        valor = {"nome_fantasia": nome_fantasia, "uf": uf, "segmento": segmento}.get(chave)
        if not (valor or "").strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"campo obrigatório: {chave}",
            )


def montar_contexto_dashboard(
    tipo: CodigoTipoTemplate,
    *,
    cnpj_basico: str,
    id_externo: str,
    nome_fantasia: str | None,
    uf: str | None,
    segmento: str | None,
    canal: CanalDashboard,
) -> dict[str, str]:
    from app.config.config import obter_configuracao

    cfg = obter_configuracao()
    corpo = _corpo_minimo(cnpj_basico, nome_fantasia)
    u = (uf or "").strip()
    seg = (segmento or "").strip()
    saudacao = _saudacao(nome_fantasia)

    if tipo in (
        CodigoTipoTemplate.APARECEU_BUSCA,
        CodigoTipoTemplate.APARECEU_BUSCA_SEM_REGISTRO,
    ):
        if canal != "email":
            raise HTTPException(status_code=400, detail="template de busca logado é só e-mail")
        if tipo == CodigoTipoTemplate.APARECEU_BUSCA_SEM_REGISTRO:
            return contexto_email_apareceu_busca_sem_registro(
                corpo, uf=u, segmento=seg, id_externo=id_externo
            )
        return contexto_email_apareceu_busca_logado(corpo, uf=u, segmento=seg, id_externo=id_externo)

    if tipo == CodigoTipoTemplate.CONSULTADO_SEM_EMAIL:
        if canal != "sms":
            raise HTTPException(status_code=400, detail="CONSULTADO_SEM_EMAIL é só SMS")
        return contexto_sms_busca(uf=u, segmento=seg, id_externo=id_externo)

    if tipo in (CodigoTipoTemplate.CREDITOS_NO_FIM, CodigoTipoTemplate.LEMBRETE_CREDITOS_ESGOTADOS):
        url_login = url_login_rastreado_para_id(id_externo)
        if canal == "email":
            return contexto_email_creditos(nome_fantasia, url_login)
        return contexto_sms_creditos(url_login)

    if tipo == CodigoTipoTemplate.APRESENTACAO:
        if canal == "email":
            return {
                "saudacao_nome": saudacao,
                "link_plataforma": cfg.url_plataforma_email,
                "url_plataforma": cfg.url_plataforma_email,
            }
        return {"url_plataforma": cfg.url_plataforma_sms}

    raise HTTPException(status_code=400, detail=f"tipo_template não suportado: {tipo.value}")


def serializar_template_dashboard(t: TemplateNotificacao) -> dict[str, Any]:
    canais: list[str] = []
    if (t.email or "").strip():
        canais.append("email")
    if (t.sms or "").strip():
        canais.append("sms")
    try:
        codigo = CodigoTipoTemplate(t.tipo)
    except ValueError:
        codigo = None
    campos = campos_contexto_para_tipo(codigo) if codigo else []
    return {
        "tipo": t.tipo,
        "canais": canais,
        "campos_contexto": campos,
        "campos_gerados_servidor": list(_GERADOS_SERVIDOR),
    }


def exigir_template_no_canal(t: TemplateNotificacao, canal: CanalDashboard) -> CodigoTipoTemplate:
    try:
        codigo = CodigoTipoTemplate(t.tipo)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"tipo de template inválido: {t.tipo}") from e
    if canal == "email" and not (t.email or "").strip():
        raise HTTPException(status_code=400, detail="template sem corpo de e-mail")
    if canal == "sms" and not (t.sms or "").strip():
        raise HTTPException(status_code=400, detail="template sem corpo de SMS")
    return codigo

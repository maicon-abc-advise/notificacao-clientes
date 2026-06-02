"""Criação de fila pendente e envio manual via dashboard."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import HTTPException, status
from redis.asyncio import Redis

from app.clique.token_clique import gerar_id_externo
from app.config.config import obter_configuracao
from app.templates.repositorio_postgres import RepositorioTemplatesPostgres
from app.mensageria.servicos.fabrica_provedor_mensagem import construir_porta_mensagem
from app.dashboard.servicos.catalogo_templates_dashboard import (
    CanalDashboard,
    exigir_template_no_canal,
    montar_contexto_dashboard,
    serializar_template_dashboard,
    validar_campos_formulario,
)
from app.dashboard.servicos.exibicao import (
    enriquecer_redis_email_pendente,
    enriquecer_redis_sms_pendente,
)
from app.dashboard.servicos.serializacao import decodificar_contexto_json_bruto
from app.mensageria.api.dto.modelos import PedidoEnvioEmail, PedidoEnvioSms
from app.mensageria.excecoes.erro import ErroEnvioZenvia
from app.mensageria.servicos.executar_envio_mensagem import executar_envio_email, executar_envio_sms
from app.orquestracao.repositorios.engajamento_consulta_repo import garantir_linha_engajamento
from app.orquestracao.repositorios.redis_emails_pendentes_repo import (
    RepositorioEmailsPendenteRedis,
    chave_hash as chave_email_pend_hash,
)
from app.orquestracao.servicos.auxiliares.enfileirar_ou_enviar_interno import (
    enfileirar_email_pendente,
    enfileirar_sms_pendente,
)
from app.reenvio.repositorios.redis_sms_pendente import RepositorioSmsPendenteRedis, chave_hash as chave_sms_pend_hash
from app.reenvio.servicos.engajamento_contatos import (
    agora_iso,
    contatos_iniciais_email,
    contatos_iniciais_sms,
    normalizar_email,
)
from app.reenvio.servicos.engajamento_fornecedor import persistir_contatos_iniciais_engajamento
from app.reenvio.servicos.n8n_claims import claim_n8n_ativo, liberar_claim_item_n8n
from app.reenvio.servicos.validacao_telefone_sms_br import normalizar_telefone_movel_br_para_sms
from app.templates.modelo import CodigoTipoTemplate

_ORIGEM_DASHBOARD = "dashboard-manual"
_CNPJ_RE = re.compile(r"^\d{8}$")

_repo_email_pend = RepositorioEmailsPendenteRedis()
_repo_sms_pend = RepositorioSmsPendenteRedis()


def _normalizar_cnpj_basico(cnpj: str) -> str:
    dig = re.sub(r"\D", "", (cnpj or "").strip())
    if not _CNPJ_RE.match(dig):
        raise HTTPException(status_code=400, detail="cnpj_basico deve ter 8 dígitos")
    return dig


def _normalizar_destinatario(canal: CanalDashboard, destinatario: str) -> str:
    d = (destinatario or "").strip()
    if not d:
        raise HTTPException(status_code=400, detail="destinatario obrigatório")
    if canal == "email":
        n = normalizar_email(d)
        if not n or "@" not in n:
            raise HTTPException(status_code=400, detail="e-mail inválido")
        return n
    tel = normalizar_telefone_movel_br_para_sms(d)
    if not tel:
        raise HTTPException(status_code=400, detail="telefone inválido para SMS")
    return tel


async def listar_templates_dashboard(pool: asyncpg.Pool, *, canal: CanalDashboard | None) -> list[dict[str, Any]]:
    repo = RepositorioTemplatesPostgres(pool)
    todos = await repo.listar_todos()
    saida: list[dict[str, Any]] = []
    for t in todos:
        item = serializar_template_dashboard(t)
        if canal and canal not in item["canais"]:
            continue
        saida.append(item)
    return saida


async def _garantir_engajamento_para_criacao(
    pool: asyncpg.Pool,
    *,
    cnpj_basico: str,
    canal: CanalDashboard,
    destinatario: str,
    nome_fantasia: str | None,
    fornecedor_id: UUID | None,
    cnpj: str | None,
) -> None:
    await garantir_linha_engajamento(
        pool,
        cnpj_basico=cnpj_basico,
        cnpj=(cnpj or "").strip() or None,
        fornecedor_id=fornecedor_id,
        nome_fantasia=(nome_fantasia or "").strip() or None,
    )
    now = agora_iso()
    if canal == "email":
        contatos = contatos_iniciais_email([destinatario], now_iso=now)
    else:
        contatos = contatos_iniciais_sms([destinatario], now_iso=now)
    await persistir_contatos_iniciais_engajamento(
        pool,
        cnpj_basico=cnpj_basico,
        fornecedor_id=fornecedor_id,
        contatos_email=contatos if canal == "email" else [],
        contatos_sms=contatos if canal == "sms" else [],
    )


async def criar_pendente_dashboard(
    pool: asyncpg.Pool,
    redis: Redis,
    *,
    canal: CanalDashboard,
    cnpj_basico: str,
    destinatario: str,
    tipo_template: CodigoTipoTemplate,
    nome_fantasia: str | None,
    uf: str | None,
    segmento: str | None,
    fornecedor_id: UUID | None,
    cnpj: str | None,
) -> dict[str, Any]:
    cnpj_b = _normalizar_cnpj_basico(cnpj_basico)
    dest = _normalizar_destinatario(canal, destinatario)

    templates = RepositorioTemplatesPostgres(pool)
    reg = await templates.obter_por_tipo(tipo_template.value)
    if reg is None:
        raise HTTPException(status_code=404, detail="template não encontrado no banco")
    codigo = exigir_template_no_canal(reg, canal)
    validar_campos_formulario(codigo, nome_fantasia=nome_fantasia, uf=uf, segmento=segmento)

    await _garantir_engajamento_para_criacao(
        pool,
        cnpj_basico=cnpj_b,
        canal=canal,
        destinatario=dest,
        nome_fantasia=nome_fantasia,
        fornecedor_id=fornecedor_id,
        cnpj=cnpj,
    )

    id_externo = gerar_id_externo()
    contexto = montar_contexto_dashboard(
        codigo,
        cnpj_basico=cnpj_b,
        id_externo=id_externo,
        nome_fantasia=nome_fantasia,
        uf=uf,
        segmento=segmento,
        canal=canal,
    )

    if canal == "email":
        pedido = PedidoEnvioEmail(
            destinatario=dest,
            tipo_template=codigo,
            contexto=contexto,
            id_externo=id_externo,
            fornecedor_id=fornecedor_id,
            cnpj_basico=cnpj_b,
        )
        ok = await enfileirar_email_pendente(redis, pedido, id_externo=id_externo, origem=_ORIGEM_DASHBOARD)
    else:
        pedido = PedidoEnvioSms(
            destinatario=dest,
            tipo_template=codigo,
            contexto=contexto,
            id_externo=id_externo,
            fornecedor_id=fornecedor_id,
            cnpj_basico=cnpj_b,
        )
        ok = await enfileirar_sms_pendente(redis, pedido, id_externo=id_externo, origem=_ORIGEM_DASHBOARD)

    if not ok:
        raise HTTPException(status_code=409, detail="id_externo já existe na fila")

    linha = await _carregar_linha_pendente(redis, canal=canal, id_externo=id_externo)
    return linha


async def _carregar_linha_pendente(redis: Redis, *, canal: CanalDashboard, id_externo: str) -> dict[str, Any]:
    key = chave_email_pend_hash(id_externo) if canal == "email" else chave_sms_pend_hash(id_externo)
    raw = await redis.hgetall(key)
    if not raw:
        raise HTTPException(status_code=404, detail="pendente não encontrado")
    ctx = decodificar_contexto_json_bruto(raw.get("contexto_json") or "{}")
    linha: dict[str, Any] = {
        "id_externo": raw.get("id_externo") or id_externo,
        "tipo_template": raw.get("tipo_template", ""),
        "contexto": ctx if isinstance(ctx, dict) else {},
        "remetente": raw.get("remetente") or None,
        "fornecedor_id": raw.get("fornecedor_id") or None,
        "cnpj_basico": raw.get("cnpj_basico") or None,
        "origem": raw.get("origem", ""),
        "consulta_id": raw.get("consulta_id") or None,
        "criado_em": raw.get("criado_em"),
        "claim_n8n_ativo": await claim_n8n_ativo(redis, canal=canal, id_externo=id_externo),
    }
    if canal == "email":
        linha["destinatario"] = raw.get("destinatario", "")
        return enriquecer_redis_email_pendente(linha)
    linha["telefone"] = raw.get("telefone", "")
    return enriquecer_redis_sms_pendente(linha)


def _pedido_email_de_hash(raw: dict[str, str], id_externo: str) -> PedidoEnvioEmail:
    ctx = json.loads(raw.get("contexto_json") or "{}")
    if not isinstance(ctx, dict):
        ctx = {}
    fid_raw = (raw.get("fornecedor_id") or "").strip()
    fid = uuid.UUID(fid_raw) if fid_raw else None
    return PedidoEnvioEmail(
        destinatario=(raw.get("destinatario") or "").strip(),
        tipo_template=CodigoTipoTemplate((raw.get("tipo_template") or "").strip()),
        contexto={str(k): str(v) for k, v in ctx.items()},
        id_externo=id_externo,
        fornecedor_id=fid,
        cnpj_basico=(raw.get("cnpj_basico") or "").strip() or None,
        remetente=(raw.get("remetente") or "").strip() or None,
    )


def _pedido_sms_de_hash(raw: dict[str, str], id_externo: str) -> PedidoEnvioSms:
    ctx = json.loads(raw.get("contexto_json") or "{}")
    if not isinstance(ctx, dict):
        ctx = {}
    fid_raw = (raw.get("fornecedor_id") or "").strip()
    fid = uuid.UUID(fid_raw) if fid_raw else None
    tel = (raw.get("telefone") or "").strip()
    return PedidoEnvioSms(
        destinatario=tel,
        tipo_template=CodigoTipoTemplate((raw.get("tipo_template") or "").strip()),
        contexto={str(k): str(v) for k, v in ctx.items()},
        id_externo=id_externo,
        fornecedor_id=fid,
        cnpj_basico=(raw.get("cnpj_basico") or "").strip() or None,
        remetente=(raw.get("remetente") or "").strip() or None,
    )


async def enviar_pendente_dashboard(
    pool: asyncpg.Pool,
    redis: Redis,
    *,
    canal: CanalDashboard,
    id_externo: str,
) -> dict[str, Any]:
    ext = (id_externo or "").strip()
    if not ext:
        raise HTTPException(status_code=400, detail="id_externo obrigatório")

    if await claim_n8n_ativo(redis, canal=canal, id_externo=ext):
        raise HTTPException(
            status_code=409,
            detail="item reservado pelo n8n (claim ativo); tente novamente em alguns minutos",
        )

    key = chave_email_pend_hash(ext) if canal == "email" else chave_sms_pend_hash(ext)
    raw = await redis.hgetall(key)
    if not raw:
        raise HTTPException(status_code=404, detail="pendente não encontrado")

    porta = construir_porta_mensagem(obter_configuracao())
    templates = RepositorioTemplatesPostgres(pool)

    try:
        if canal == "email":
            pedido = _pedido_email_de_hash(raw, ext)
            resultado = await executar_envio_email(pool, pedido, porta=porta, templates=templates)
            await _repo_email_pend.remover(redis, ext)
        else:
            pedido = _pedido_sms_de_hash(raw, ext)
            resultado = await executar_envio_sms(pool, redis, pedido, porta=porta, templates=templates)
            await _repo_sms_pend.remover(redis, ext)
    except ErroEnvioZenvia as e:
        raise HTTPException(status_code=502, detail=str(e)[:2000]) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    finally:
        await liberar_claim_item_n8n(redis, canal=canal, id_externo=ext)

    return {
        "id_externo": ext,
        "canal": canal,
        "id_provedor": resultado.id_provedor,
        "resposta_parcial": resultado.resposta_parcial,
    }

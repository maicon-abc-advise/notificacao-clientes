"""Criação de pendentes e envio manual (dashboard autenticado)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query

from app.dashboard.api.dto.envio_manual_dashboard import (
    CorpoCriarPendenteDashboard,
    CorpoEnviarPendenteDashboard,
)
from app.dashboard.servicos import envio_manual_dashboard_servico as s
from app.iam.rotas.dashboard_rotas import usuario_logado
from app.orquestracao.api.dependencias import PoolOrquestracao, RedisOrquestracao
router = APIRouter(
    prefix="/v1/interno/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(usuario_logado)],
)


@router.get("/templates-notificacao")
async def get_templates_notificacao(
    pool: PoolOrquestracao,
    canal: Annotated[Literal["email", "sms"] | None, Query()] = None,
) -> dict[str, Any]:
    itens = await s.listar_templates_dashboard(pool, canal=canal)
    return {"itens": itens}


@router.post("/emails/redis-pendentes", status_code=201)
async def post_criar_email_pendente(
    pool: PoolOrquestracao,
    redis: RedisOrquestracao,
    body: CorpoCriarPendenteDashboard,
) -> dict[str, Any]:
    item = await s.criar_pendente_dashboard(
        pool,
        redis,
        canal="email",
        cnpj_basico=body.cnpj_basico,
        destinatario=body.destinatario,
        tipo_template=body.tipo_template,
        nome_fantasia=body.nome_fantasia,
        uf=body.uf,
        segmento=body.segmento,
        fornecedor_id=body.fornecedor_id,
        cnpj=body.cnpj,
    )
    return {"origem": "redis", "tabela_logica": "emails_pendentes", "item": item}


@router.post("/sms/redis-pendentes", status_code=201)
async def post_criar_sms_pendente(
    pool: PoolOrquestracao,
    redis: RedisOrquestracao,
    body: CorpoCriarPendenteDashboard,
) -> dict[str, Any]:
    item = await s.criar_pendente_dashboard(
        pool,
        redis,
        canal="sms",
        cnpj_basico=body.cnpj_basico,
        destinatario=body.destinatario,
        tipo_template=body.tipo_template,
        nome_fantasia=body.nome_fantasia,
        uf=body.uf,
        segmento=body.segmento,
        fornecedor_id=body.fornecedor_id,
        cnpj=body.cnpj,
    )
    return {"origem": "redis", "tabela_logica": "sms_pendentes", "item": item}


@router.post("/emails/redis-pendentes/{id_externo:path}/enviar")
async def post_enviar_email_pendente(
    id_externo: str,
    pool: PoolOrquestracao,
    redis: RedisOrquestracao,
    body: CorpoEnviarPendenteDashboard,
    sessao: Annotated[dict[str, Any], Depends(usuario_logado)],
) -> dict[str, Any]:
    from app.dashboard.servicos.mutacoes_dashboard_servico import _exigir_senha

    _exigir_senha(sessao, body.senha)
    return await s.enviar_pendente_dashboard(pool, redis, canal="email", id_externo=id_externo)


@router.post("/sms/redis-pendentes/{id_externo:path}/enviar")
async def post_enviar_sms_pendente(
    id_externo: str,
    pool: PoolOrquestracao,
    redis: RedisOrquestracao,
    body: CorpoEnviarPendenteDashboard,
    sessao: Annotated[dict[str, Any], Depends(usuario_logado)],
) -> dict[str, Any]:
    from app.dashboard.servicos.mutacoes_dashboard_servico import _exigir_senha

    _exigir_senha(sessao, body.senha)
    return await s.enviar_pendente_dashboard(pool, redis, canal="sms", id_externo=id_externo)

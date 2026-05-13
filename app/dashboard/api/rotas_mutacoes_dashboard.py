"""Mutações do dashboard (PATCH/DELETE) — autenticação interna."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends

from app.dashboard.api.dto.mutacoes_dashboard import CorpoConfirmacaoSenha
from app.dashboard.servicos import mutacoes_dashboard_servico as m
from app.iam.rotas.dashboard_rotas import usuario_logado
from app.orquestracao.api.dependencias import PoolOrquestracao, RedisOrquestracao

router = APIRouter(
    prefix="/v1/interno/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(usuario_logado)],
)

SessaoDashboard = Annotated[dict[str, Any], Depends(usuario_logado)]


@router.patch("/emails/postgres/{registro_id}")
async def patch_emails_postgres(
    registro_id: uuid.UUID,
    pool: PoolOrquestracao,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    return await m.patch_postgres_tabela(
        pool,
        tabela_logica="emails_enviados",
        pk_coluna="id",
        pk_valor=registro_id,
        body=body,
        bloqueadas={"id"},
        canal_enriquecer="email",
    )


@router.delete("/emails/postgres/{registro_id}", status_code=204)
async def delete_emails_postgres(
    registro_id: uuid.UUID,
    pool: PoolOrquestracao,
    sessao: SessaoDashboard,
    payload: CorpoConfirmacaoSenha,
) -> None:
    await m.delete_postgres_tabela(
        pool,
        tabela_logica="emails_enviados",
        pk_coluna="id",
        pk_valor=registro_id,
        sessao=sessao,
        senha=payload.senha,
    )


@router.patch("/sms/postgres/{registro_id}")
async def patch_sms_postgres(
    registro_id: uuid.UUID,
    pool: PoolOrquestracao,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    return await m.patch_postgres_tabela(
        pool,
        tabela_logica="sms_enviados",
        pk_coluna="id",
        pk_valor=registro_id,
        body=body,
        bloqueadas={"id"},
        canal_enriquecer="sms",
    )


@router.delete("/sms/postgres/{registro_id}", status_code=204)
async def delete_sms_postgres(
    registro_id: uuid.UUID,
    pool: PoolOrquestracao,
    sessao: SessaoDashboard,
    payload: CorpoConfirmacaoSenha,
) -> None:
    await m.delete_postgres_tabela(
        pool,
        tabela_logica="sms_enviados",
        pk_coluna="id",
        pk_valor=registro_id,
        sessao=sessao,
        senha=payload.senha,
    )


@router.patch("/engajamento/fornecedores/{cnpj_basico}")
async def patch_engajamento_fornecedor(
    cnpj_basico: str,
    pool: PoolOrquestracao,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    return await m.patch_postgres_tabela(
        pool,
        tabela_logica="engajamento_fornecedores",
        pk_coluna="cnpj_basico",
        pk_valor=cnpj_basico,
        body=body,
        bloqueadas={"cnpj_basico"},
        canal_enriquecer=None,
    )


@router.delete("/engajamento/fornecedores/{cnpj_basico}", status_code=204)
async def delete_engajamento_fornecedor(
    cnpj_basico: str,
    pool: PoolOrquestracao,
    sessao: SessaoDashboard,
    payload: CorpoConfirmacaoSenha,
) -> None:
    await m.delete_postgres_tabela(
        pool,
        tabela_logica="engajamento_fornecedores",
        pk_coluna="cnpj_basico",
        pk_valor=cnpj_basico,
        sessao=sessao,
        senha=payload.senha,
    )


@router.patch("/emails/redis-pendentes/{id_externo:path}")
async def patch_emails_redis_pendentes(
    id_externo: str,
    redis: RedisOrquestracao,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    return await m.patch_redis_email_pendente(redis, id_externo, body)


@router.delete("/emails/redis-pendentes/{id_externo:path}", status_code=204)
async def delete_emails_redis_pendentes(
    id_externo: str,
    redis: RedisOrquestracao,
    sessao: SessaoDashboard,
    payload: CorpoConfirmacaoSenha,
) -> None:
    await m.delete_redis_email_pendente(redis, id_externo, sessao, payload.senha)


@router.patch("/emails/redis-esperando-confirmacao/{message_id:path}")
async def patch_emails_redis_esperando(
    message_id: str,
    redis: RedisOrquestracao,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    return await m.patch_redis_email_esperando(redis, message_id, body)


@router.delete("/emails/redis-esperando-confirmacao/{message_id:path}", status_code=204)
async def delete_emails_redis_esperando(
    message_id: str,
    redis: RedisOrquestracao,
    sessao: SessaoDashboard,
    payload: CorpoConfirmacaoSenha,
) -> None:
    await m.delete_redis_email_esperando(redis, message_id, sessao, payload.senha)


@router.patch("/sms/redis-pendentes/{id_externo:path}")
async def patch_sms_redis_pendentes(
    id_externo: str,
    redis: RedisOrquestracao,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    return await m.patch_redis_sms_pendente(redis, id_externo, body)


@router.delete("/sms/redis-pendentes/{id_externo:path}", status_code=204)
async def delete_sms_redis_pendentes(
    id_externo: str,
    redis: RedisOrquestracao,
    sessao: SessaoDashboard,
    payload: CorpoConfirmacaoSenha,
) -> None:
    await m.delete_redis_sms_pendente(redis, id_externo, sessao, payload.senha)


@router.patch("/sms/redis-esperando-confirmacao/{message_id:path}")
async def patch_sms_redis_esperando(
    message_id: str,
    redis: RedisOrquestracao,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    return await m.patch_redis_sms_esperando(redis, message_id, body)


@router.delete("/sms/redis-esperando-confirmacao/{message_id:path}", status_code=204)
async def delete_sms_redis_esperando(
    message_id: str,
    redis: RedisOrquestracao,
    sessao: SessaoDashboard,
    payload: CorpoConfirmacaoSenha,
) -> None:
    await m.delete_redis_sms_esperando(redis, message_id, sessao, payload.senha)

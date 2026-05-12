"""Endpoints de leitura para o dashboard (autenticação interna)."""

from __future__ import annotations
import math
from typing import Annotated, Any
from fastapi import APIRouter, Depends, Query

from app.config.postgres_identificadores import obter_identificadores_postgres
from app.dashboard.servicos.exibicao import (
    enriquecer_linha_postgres,
    enriquecer_redis_email_esperando,
    enriquecer_redis_email_pendente,
    enriquecer_redis_sms_esperando,
    enriquecer_redis_sms_pendente,
)
from app.dashboard.servicos.serializacao import decodificar_contexto_json_bruto, registo_para_json
from app.iam.rotas.dashboard_rotas import usuario_logado
from app.orquestracao.api.dependencias import PoolOrquestracao, RedisOrquestracao
from app.orquestracao.repositorios.redis_emails_pendentes_repo import KEY_INDEX as IDX_EMAIL_PEND
from app.orquestracao.repositorios.redis_emails_pendentes_repo import chave_hash as chave_email_pend
from app.reenvio.repositorios.redis_emails_esperando_confirmacao import KEY_SWEEP as IDX_EMAIL_CONF
from app.reenvio.repositorios.redis_emails_esperando_confirmacao import chave_hash as chave_email_conf
from app.reenvio.repositorios.redis_sms_esperando_confirmacao import KEY_SWEEP as IDX_SMS_CONF
from app.reenvio.repositorios.redis_sms_esperando_confirmacao import chave_hash as chave_sms_conf
from app.reenvio.repositorios.redis_sms_pendente import KEY_INDEX as IDX_SMS_PEND
from app.reenvio.repositorios.redis_sms_pendente import chave_hash as chave_sms_pend

router = APIRouter(
    prefix="/v1/interno/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(usuario_logado)],
)

PAGE_SIZE = 10

def _page_clamped(page: int) -> int:
    return max(1, page)

def _meta(total: int, page: int) -> dict[str, int]:
    return {
        "total": total,
        "page": page,
        "page_size": PAGE_SIZE,
        "total_pages": max(1, math.ceil(total / PAGE_SIZE)) if total else 1,
    }

def _h(raw: dict[Any, Any], key: str) -> str | None:
    """Lê campo de hash Redis com chaves/valores str ou bytes."""
    if not raw:
        return None
    for rk, rv in raw.items():
        ks = rk.decode() if isinstance(rk, bytes) else str(rk)
        if ks != key:
            continue
        if rv is None:
            return None
        if isinstance(rv, bytes):
            return rv.decode(errors="replace")
        return str(rv)
    return None

@router.get("/emails/metricas")
async def metricas_emails(
    pool: PoolOrquestracao,
    redis: RedisOrquestracao,
) -> dict[str, Any]:
    p = obter_identificadores_postgres()
    te = p.qual("emails_enviados")
    total = int(await pool.fetchval(f"SELECT COUNT(*) FROM {te}") or 0)
    falhas = int(
        await pool.fetchval(
            f"SELECT COUNT(*) FROM {te} WHERE status_ultimo = 'falha_definitiva'",
        )
        or 0,
    )
    lidos = int(
        await pool.fetchval(
            f"SELECT COUNT(*) FROM {te} WHERE status_ultimo = 'lido'",
        )
        or 0,
    )
    clicados = int(
        await pool.fetchval(
            f"SELECT COUNT(*) FROM {te} WHERE status_ultimo = 'clicado'",
        )
        or 0,
    )
    pendentes = int(await redis.zcard(IDX_EMAIL_PEND) or 0)
    esperando = int(await redis.zcard(IDX_EMAIL_CONF) or 0)
    return {
        "emails_enviados_total": total,
        "emails_pendentes_pre_envio": pendentes,
        "emails_esperando_confirmacao": esperando,
        "emails_falha_definitiva": falhas,
        "emails_lidos": lidos,
        "emails_clicados": clicados,
        "cartoes": [
            {"chave": "enviados", "valor": total, "legenda": "E-mails registados"},
            {"chave": "pendentes", "valor": pendentes, "legenda": "Na fila pré-envio"},
            {"chave": "recusados", "valor": falhas, "legenda": "Falha definitiva"},
            {"chave": "esperando_feedback", "valor": esperando, "legenda": "Esperando confirmação"},
            {"chave": "abertos", "valor": lidos, "legenda": "E-mails lidos"},
            {"chave": "cliques", "valor": clicados, "legenda": "Link clicado (e-mail)"},
        ],
    }


@router.get("/emails/postgres")
async def lista_emails_postgres(
    pool: PoolOrquestracao,
    page: Annotated[int, Query(ge=1)] = 1,
) -> dict[str, Any]:
    p = obter_identificadores_postgres()
    te = p.qual("emails_enviados")
    page = _page_clamped(page)
    offset = (page - 1) * PAGE_SIZE
    total = int(await pool.fetchval(f"SELECT COUNT(*) FROM {te}") or 0)
    rows = await pool.fetch(
        f"""
        SELECT * FROM {te}
        ORDER BY criado_em DESC NULLS LAST, id DESC
        LIMIT {PAGE_SIZE} OFFSET {offset}
        """,
    )
    itens = [enriquecer_linha_postgres(registo_para_json(r), canal="email") for r in rows]
    return {"origem": "postgres", "tabela_logica": "emails_enviados", "itens": itens, **_meta(total, page)}


@router.get("/emails/redis-pendentes")
async def lista_emails_redis_pendentes(
    redis: RedisOrquestracao,
    page: Annotated[int, Query(ge=1)] = 1,
) -> dict[str, Any]:
    page = _page_clamped(page)
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE - 1
    total = int(await redis.zcard(IDX_EMAIL_PEND) or 0)
    ids_raw = await redis.zrevrange(IDX_EMAIL_PEND, start, end)
    itens: list[dict[str, Any]] = []
    for ext in ids_raw:
        ext_s = ext.decode() if isinstance(ext, bytes) else str(ext)
        raw = await redis.hgetall(chave_email_pend(ext_s))
        if not raw:
            await redis.zrem(IDX_EMAIL_PEND, ext_s)
            continue
        ctx = decodificar_contexto_json_bruto(_h(raw, "contexto_json"))
        linha: dict[str, Any] = {
            "id_externo": _h(raw, "id_externo") or _h(raw, "external_id") or ext_s,
            "destinatario": _h(raw, "destinatario"),
            "tipo_template": _h(raw, "tipo_template"),
            "contexto": ctx if isinstance(ctx, dict) else {},
            "remetente": _h(raw, "remetente") or None,
            "fornecedor_id": _h(raw, "fornecedor_id") or _h(raw, "usuario_id") or None,
            "cnpj_basico": _h(raw, "cnpj_basico") or None,
            "origem": _h(raw, "origem"),
            "consulta_id": _h(raw, "consulta_id") or None,
            "criado_em": _h(raw, "criado_em"),
        }
        itens.append(enriquecer_redis_email_pendente(linha))
    return {"origem": "redis", "tabela_logica": "emails_pendentes", "itens": itens, **_meta(total, page)}


@router.get("/emails/redis-esperando-confirmacao")
async def lista_emails_redis_esperando(
    redis: RedisOrquestracao,
    page: Annotated[int, Query(ge=1)] = 1,
) -> dict[str, Any]:
    page = _page_clamped(page)
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE - 1
    total = int(await redis.zcard(IDX_EMAIL_CONF) or 0)
    ids_raw = await redis.zrevrange(IDX_EMAIL_CONF, start, end)
    itens: list[dict[str, Any]] = []
    for mid in ids_raw:
        mid_s = mid.decode() if isinstance(mid, bytes) else str(mid)
        raw = await redis.hgetall(chave_email_conf(mid_s))
        if not raw:
            await redis.zrem(IDX_EMAIL_CONF, mid_s)
            continue
        ctx = decodificar_contexto_json_bruto(_h(raw, "contexto_json"))
        linha = {
            "message_id_zenvia": mid_s,
            "id_externo": _h(raw, "id_externo") or _h(raw, "external_id"),
            "email_destinatario": _h(raw, "email_destinatario"),
            "tipo_template": _h(raw, "tipo_template"),
            "contexto": ctx if isinstance(ctx, dict) else {},
            "remetente": _h(raw, "remetente") or None,
            "fornecedor_id": _h(raw, "fornecedor_id") or _h(raw, "usuario_id") or None,
            "cnpj_basico": _h(raw, "cnpj_basico") or None,
            "consulta_id": _h(raw, "consulta_id") or None,
            "status_atual": _h(raw, "status_atual"),
            "criado_em": _h(raw, "criado_em"),
            "atualizado_em": _h(raw, "atualizado_em"),
            "ultimo_cause": _h(raw, "ultimo_cause"),
        }
        itens.append(enriquecer_redis_email_esperando(linha))
    return {
        "origem": "redis",
        "tabela_logica": "emails_esperando_confirmacao",
        "itens": itens,
        **_meta(total, page),
    }


@router.get("/sms/metricas")
async def metricas_sms(
    pool: PoolOrquestracao,
    redis: RedisOrquestracao,
) -> dict[str, Any]:
    p = obter_identificadores_postgres()
    ts = p.qual("sms_enviados")
    total = int(await pool.fetchval(f"SELECT COUNT(*) FROM {ts}") or 0)
    falhas = int(
        await pool.fetchval(
            f"SELECT COUNT(*) FROM {ts} WHERE status_ultimo = 'falha_definitiva'",
        )
        or 0,
    )
    lidos = int(
        await pool.fetchval(
            f"SELECT COUNT(*) FROM {ts} WHERE status_ultimo = 'lido'",
        )
        or 0,
    )
    clicados = int(
        await pool.fetchval(
            f"SELECT COUNT(*) FROM {ts} WHERE status_ultimo = 'clicado'",
        )
        or 0,
    )
    pendentes = int(await redis.zcard(IDX_SMS_PEND) or 0)
    esperando = int(await redis.zcard(IDX_SMS_CONF) or 0)
    return {
        "sms_enviados_total": total,
        "sms_pendentes_fila": pendentes,
        "sms_esperando_confirmacao": esperando,
        "sms_falha_definitiva": falhas,
        "sms_lidos": lidos,
        "sms_clicados": clicados,
        "cartoes": [
            {"chave": "enviados", "valor": total, "legenda": "SMS registados"},
            {"chave": "pendentes", "valor": pendentes, "legenda": "Na fila a enviar"},
            {"chave": "esperando_feedback", "valor": esperando, "legenda": "Esperando confirmação"},
            {"chave": "recusados", "valor": falhas, "legenda": "Falha definitiva"},
            {"chave": "abertos", "valor": lidos, "legenda": "SMS lidos"},
            {"chave": "cliques", "valor": clicados, "legenda": "Link clicado (SMS)"},
        ],
    }

@router.get("/sms/postgres")
async def lista_sms_postgres(
    pool: PoolOrquestracao,
    page: Annotated[int, Query(ge=1)] = 1,
) -> dict[str, Any]:
    p = obter_identificadores_postgres()
    ts = p.qual("sms_enviados")
    page = _page_clamped(page)
    offset = (page - 1) * PAGE_SIZE
    total = int(await pool.fetchval(f"SELECT COUNT(*) FROM {ts}") or 0)
    rows = await pool.fetch(
        f"""
        SELECT * FROM {ts}
        ORDER BY criado_em DESC NULLS LAST, id DESC
        LIMIT {PAGE_SIZE} OFFSET {offset}
        """,
    )
    itens = [enriquecer_linha_postgres(registo_para_json(r), canal="sms") for r in rows]
    return {"origem": "postgres", "tabela_logica": "sms_enviados", "itens": itens, **_meta(total, page)}

@router.get("/sms/redis-pendentes")
async def lista_sms_redis_pendentes(
    redis: RedisOrquestracao,
    page: Annotated[int, Query(ge=1)] = 1,
) -> dict[str, Any]:
    page = _page_clamped(page)
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE - 1
    total = int(await redis.zcard(IDX_SMS_PEND) or 0)
    ids_raw = await redis.zrevrange(IDX_SMS_PEND, start, end)
    itens: list[dict[str, Any]] = []
    for ext in ids_raw:
        ext_s = ext.decode() if isinstance(ext, bytes) else str(ext)
        raw = await redis.hgetall(chave_sms_pend(ext_s))
        if not raw:
            await redis.zrem(IDX_SMS_PEND, ext_s)
            continue
        ctx = decodificar_contexto_json_bruto(_h(raw, "contexto_json"))
        linha = {
            "id_externo": _h(raw, "id_externo") or _h(raw, "external_id") or ext_s,
            "telefone": _h(raw, "telefone"),
            "tipo_template": _h(raw, "tipo_template"),
            "contexto": ctx if isinstance(ctx, dict) else {},
            "remetente": _h(raw, "remetente") or None,
            "origem": _h(raw, "origem"),
            "fornecedor_id": _h(raw, "fornecedor_id") or _h(raw, "usuario_id") or None,
            "cnpj_basico": _h(raw, "cnpj_basico") or None,
            "consulta_id": _h(raw, "consulta_id") or None,
            "criado_em": _h(raw, "criado_em"),
        }
        itens.append(enriquecer_redis_sms_pendente(linha))
    return {"origem": "redis", "tabela_logica": "sms_pendentes", "itens": itens, **_meta(total, page)}

@router.get("/sms/redis-esperando-confirmacao")
async def lista_sms_redis_esperando(
    redis: RedisOrquestracao,
    page: Annotated[int, Query(ge=1)] = 1,
) -> dict[str, Any]:
    page = _page_clamped(page)
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE - 1
    total = int(await redis.zcard(IDX_SMS_CONF) or 0)
    ids_raw = await redis.zrevrange(IDX_SMS_CONF, start, end)
    itens: list[dict[str, Any]] = []
    for mid in ids_raw:
        mid_s = mid.decode() if isinstance(mid, bytes) else str(mid)
        raw = await redis.hgetall(chave_sms_conf(mid_s))
        if not raw:
            await redis.zrem(IDX_SMS_CONF, mid_s)
            continue
        ctx = decodificar_contexto_json_bruto(_h(raw, "contexto_json"))
        linha = {
            "message_id_zenvia": mid_s,
            "id_externo": _h(raw, "id_externo") or _h(raw, "external_id"),
            "telefone_destinatario": _h(raw, "telefone_destinatario"),
            "tipo_template": _h(raw, "tipo_template"),
            "contexto": ctx if isinstance(ctx, dict) else {},
            "remetente": _h(raw, "remetente") or None,
            "fornecedor_id": _h(raw, "fornecedor_id") or _h(raw, "usuario_id") or None,
            "cnpj_basico": _h(raw, "cnpj_basico") or None,
            "consulta_id": _h(raw, "consulta_id") or None,
            "status_atual": _h(raw, "status_atual"),
            "criado_em": _h(raw, "criado_em"),
            "atualizado_em": _h(raw, "atualizado_em"),
        }
        itens.append(enriquecer_redis_sms_esperando(linha))
    return {
        "origem": "redis",
        "tabela_logica": "sms_esperando_confirmacao",
        "itens": itens,
        **_meta(total, page),
    }

@router.get("/engajamento/fornecedores")
async def lista_engajamento_fornecedores(
    pool: PoolOrquestracao,
    page: Annotated[int, Query(ge=1)] = 1,
) -> dict[str, Any]:
    p = obter_identificadores_postgres()
    te = p.qual("engajamento_fornecedores")
    tf = p.qual("fornecedores")
    page = _page_clamped(page)
    offset = (page - 1) * PAGE_SIZE
    total = int(await pool.fetchval(f"SELECT COUNT(*) FROM {te}") or 0)
    rows = await pool.fetch(
        f"""
        SELECT e.*, COALESCE(f.nome, e.nome_fantasia) AS nome_fornecedor
        FROM {te} AS e
        LEFT JOIN {tf} AS f ON f.cnpj_basico = e.cnpj_basico
        ORDER BY e.engajamento_atualizado_em DESC NULLS LAST, e.cnpj_basico DESC
        LIMIT {PAGE_SIZE} OFFSET {offset}
        """,
    )
    itens = [registo_para_json(r) for r in rows]
    return {
        "origem": "postgres",
        "tabela_logica": "engajamento_fornecedores",
        "itens": itens,
        **_meta(total, page),
    }

"""Primeiro clique em link (GET /v1/clique ou webhook Zenvia CLICKED)."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any
from urllib.parse import urlencode

import asyncpg
from redis.asyncio import Redis

from app.config.config import Configuracao
from app.config.postgres_identificadores import obter_identificadores_postgres
from app.mensageria.repositorios.postgres_emails_enviados import (
    atualizar_status_por_id_externo as atualizar_status_email_por_id_externo,
    atualizar_status_por_id_mensagem_zenvia,
    buscar_por_id_externo as buscar_email_por_id_externo,
)
from app.mensageria.repositorios.postgres_sms_enviados import (
    atualizar_status_por_id_externo as atualizar_status_sms_por_id_externo,
    atualizar_status_por_id_interno,
    buscar_por_id_externo as buscar_sms_por_id_externo,
)
from app.reenvio.repositorios.redis_emails_esperando_confirmacao import (
    RepositorioEmailsEsperandoConfirmacaoRedis,
)
from app.reenvio.repositorios.redis_sms_esperando_confirmacao import (
    RepositorioSmsEsperandoConfirmacaoRedis,
)
from app.orquestracao.servicos.comprador_busca_constantes import eh_sms_comprador
from app.reenvio.servicos.engajamento_estado import EngajamentoEmailEstado, EngajamentoSmsEstado
from app.reenvio.servicos.engajamento_fornecedor import parse_fornecedor_id, tocar_engajamento_email, tocar_engajamento_sms


_log = logging.getLogger(__name__)

_STATUS_CLICADO = "clicado"
_NOME_EMPRESA_PADRAO = "Sua empresa"


def _parse_contexto(raw: Any) -> dict[str, str]:
    if raw is None:
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items() if v is not None}


async def buscar_nome_fantasia_engajamento(pool: asyncpg.Pool, cnpj_basico: str | None) -> str:
    cnpj = (cnpj_basico or "").strip()
    if not cnpj:
        return ""
    p = obter_identificadores_postgres()
    te = p.qual("engajamento_fornecedores")
    row = await pool.fetchrow(
        f"SELECT nome_fantasia FROM {te} WHERE cnpj_basico = $1 LIMIT 1",
        cnpj,
    )
    if row is None:
        return ""
    return (row["nome_fantasia"] or "").strip()


def montar_url_landing_info_consulta(
    cfg: Configuracao,
    *,
    segmento: str,
    uf: str,
    nome_empresa: str,
) -> str:
    base = (cfg.url_landing_info_consulta or "").strip().rstrip("/")
    nome = (nome_empresa or "").strip() or _NOME_EMPRESA_PADRAO
    params = {
        "segmento": (segmento or "").strip(),
        "uf": (uf or "").strip(),
        "nome_empresa": nome,
    }
    return f"{base}?{urlencode(params)}"


def _nome_empresa_resposta(nome_fantasia: str) -> str:
    return (nome_fantasia or "").strip() or _NOME_EMPRESA_PADRAO


async def _buscar_linha_envio_por_id_externo(
    pool: asyncpg.Pool, id_externo: str
) -> asyncpg.Record | None:
    row = await buscar_email_por_id_externo(pool, id_externo)
    if row is None:
        row = await buscar_sms_por_id_externo(pool, id_externo)
    return row


async def obter_dados_clique_de_row(pool: asyncpg.Pool, row: asyncpg.Record) -> dict[str, str]:
    ctx = _parse_contexto(row["contexto"])
    cnpj = (row.get("cnpj_basico") or ctx.get("cnpj_basico") or "").strip() or None
    nome = await buscar_nome_fantasia_engajamento(pool, cnpj)
    return {
        "uf": (ctx.get("uf") or "").strip(),
        "segmento": (ctx.get("segmento") or "").strip(),
        "nome_empresa": _nome_empresa_resposta(nome),
    }


async def obter_dados_clique_por_id_externo(
    pool: asyncpg.Pool, id_externo: str
) -> dict[str, str] | None:
    row = await _buscar_linha_envio_por_id_externo(pool, id_externo)
    if row is None:
        return None
    return await obter_dados_clique_de_row(pool, row)


async def processar_clique_api(
    pool: asyncpg.Pool,
    redis: Redis,
    id_externo: str,
    *,
    message_id_zenvia: str | None = None,
) -> dict[str, str] | None:
    """Dados para o front; registra primeiro clique se ainda não ``clicado``."""
    row = await _buscar_linha_envio_por_id_externo(pool, id_externo)
    if row is None:
        return None
    dados = await obter_dados_clique_de_row(pool, row)
    await registrar_primeiro_clique_por_id_externo(
        pool, redis, id_externo, message_id_zenvia=message_id_zenvia
    )
    return dados


async def montar_redirect_para_id_externo(
    pool: asyncpg.Pool,
    cfg: Configuracao,
    id_externo: str,
) -> str | None:
    """Monta URL da landing; ``None`` se ``id_externo`` não existir em email nem SMS."""
    dados = await obter_dados_clique_por_id_externo(pool, id_externo)
    if dados is None:
        return None
    return montar_url_landing_info_consulta(
        cfg,
        segmento=dados["segmento"],
        uf=dados["uf"],
        nome_empresa=dados["nome_empresa"],
    )


def _ja_clicado(row: asyncpg.Record) -> bool:
    return (row.get("status_ultimo") or "").strip().lower() == _STATUS_CLICADO


async def _remover_redis_email(redis: Redis, *, id_externo: str, message_id: str | None) -> None:
    repo = RepositorioEmailsEsperandoConfirmacaoRedis()
    mid = (message_id or "").strip()
    if not mid:
        mid = await redis.get(f"emails-esperando-confirmacao:id_externo:{id_externo}")
        if isinstance(mid, bytes):
            mid = mid.decode()
        mid = (mid or "").strip()
    if mid:
        await repo.remover(redis, mid)


async def _remover_redis_sms(redis: Redis, *, id_externo: str, message_id: str | None) -> None:
    repo = RepositorioSmsEsperandoConfirmacaoRedis()
    mid = (message_id or "").strip()
    if not mid:
        mid = await redis.get(f"sms-esperando-confirmacao:id_externo:{id_externo}")
        if isinstance(mid, bytes):
            mid = mid.decode()
        mid = (mid or "").strip()
    if mid:
        await repo.remover(redis, mid)


async def registrar_primeiro_clique_email(
    pool: asyncpg.Pool,
    redis: Redis,
    row: asyncpg.Record,
    *,
    message_id_zenvia: str | None = None,
) -> bool:
    """Registra primeiro clique (e-mail). Retorna ``True`` se aplicou efeitos colaterais."""
    if _ja_clicado(row):
        return False
    id_externo = row["id_externo"]
    mid = (row.get("id_mensagem_zenvia") or message_id_zenvia or "").strip() or None
    p = obter_identificadores_postgres()
    fid = parse_fornecedor_id(str(row[p.col_fornecedor_id]) if row.get(p.col_fornecedor_id) else None)
    cnpj = (row.get("cnpj_basico") or "").strip() or None
    dest = (row.get("email_destinatario") or "").strip() or None
    if mid:
        await atualizar_status_por_id_mensagem_zenvia(
            pool, id_mensagem_zenvia=mid, status_ultimo=_STATUS_CLICADO
        )
    else:
        await atualizar_status_email_por_id_externo(
            pool, id_externo=id_externo, status_ultimo=_STATUS_CLICADO
        )
    await tocar_engajamento_email(
        pool, fid, cnpj, EngajamentoEmailEstado.EMAIL_LINK_CLICADO, endereco=dest
    )
    await _remover_redis_email(redis, id_externo=id_externo, message_id=mid)
    _log.info("Primeiro clique e-mail registrado id_externo=%s", id_externo)
    return True


async def registrar_primeiro_clique_por_id_externo(
    pool: asyncpg.Pool,
    redis: Redis,
    id_externo: str,
    *,
    message_id_zenvia: str | None = None,
) -> bool:
    """Tenta e-mail, depois SMS. Retorna ``True`` se registrou primeiro clique."""
    row_e = await buscar_email_por_id_externo(pool, id_externo)
    if row_e is not None:
        return await registrar_primeiro_clique_email(
            pool, redis, row_e, message_id_zenvia=message_id_zenvia
        )
    row_s = await buscar_sms_por_id_externo(pool, id_externo)
    if row_s is not None:
        return await registrar_primeiro_clique_sms(
            pool, redis, row_s, message_id_zenvia=message_id_zenvia
        )
    return False


async def registrar_primeiro_clique_sms(
    pool: asyncpg.Pool,
    redis: Redis,
    row: asyncpg.Record,
    *,
    message_id_zenvia: str | None = None,
) -> bool:
    if _ja_clicado(row):
        return False
    id_externo = row["id_externo"]
    mid = (row.get("id_mensagem_zenvia") or message_id_zenvia or "").strip() or None
    p = obter_identificadores_postgres()
    fid = parse_fornecedor_id(str(row[p.col_fornecedor_id]) if row.get(p.col_fornecedor_id) else None)
    cnpj = (row.get("cnpj_basico") or "").strip() or None
    dest = (row.get("telefone") or "").strip() or None
    id_interno = row.get("id")
    if id_interno is not None:
        await atualizar_status_por_id_interno(
            pool,
            id_interno=id_interno if isinstance(id_interno, uuid.UUID) else uuid.UUID(str(id_interno)),
            status_ultimo=_STATUS_CLICADO,
            motivo=None,
        )
    else:
        await atualizar_status_sms_por_id_externo(
            pool, id_externo=id_externo, status_ultimo=_STATUS_CLICADO
        )
    if not eh_sms_comprador(str(row.get("tipo_template") or "")):
        await tocar_engajamento_sms(
            pool, fid, cnpj, EngajamentoSmsEstado.SMS_LINK_CLICADO, endereco=dest
        )
    await _remover_redis_sms(redis, id_externo=id_externo, message_id=mid)
    _log.info("Primeiro clique SMS registrado id_externo=%s", id_externo)
    return True


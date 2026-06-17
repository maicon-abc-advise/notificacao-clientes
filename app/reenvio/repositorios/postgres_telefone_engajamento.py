"""Persistência de telefones por canal em ``telefone_engajamento``."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import asyncpg

from app.config.postgres_identificadores import obter_identificadores_postgres
from app.reenvio.servicos.engajamento_contatos import (
    agora_iso,
    fundir_lista_contatos_sms,
    normalizar_telefone,
    parse_contatos_json,
)
from app.reenvio.servicos.engajamento_estado import EngajamentoSmsEstado

CANAL_SMS = "sms"
_Executor = asyncpg.Connection | asyncpg.Pool


def _tabela() -> str:
    return obter_identificadores_postgres().qual("telefone_engajamento")


def _linha_para_contato(row: asyncpg.Record) -> dict[str, Any]:
    atualizado = row["atualizado_em"]
    if isinstance(atualizado, datetime):
        ts = atualizado if atualizado.tzinfo else atualizado.replace(tzinfo=UTC)
        ultima = ts.isoformat()
    else:
        ultima = agora_iso()
    return {
        "endereco": str(row["telefone"]),
        "estado": str(row["status"]),
        "ultima_atualizacao_em": ultima,
    }


def _parse_atualizado_em(val: Any) -> datetime:
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=UTC)
    if isinstance(val, str):
        bruto = val.strip()
        if bruto:
            try:
                dt = datetime.fromisoformat(bruto.replace("Z", "+00:00"))
                return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
            except ValueError:
                pass
    return datetime.now(UTC)


async def listar_contatos_sms(
    executor: _Executor,
    cnpj_basico: str,
) -> list[dict[str, Any]]:
    cnpj = (cnpj_basico or "").strip()
    if not cnpj:
        return []
    rows = await executor.fetch(
        f"""
        SELECT telefone, status, atualizado_em
        FROM {_tabela()}
        WHERE cnpj_basico = $1 AND canal = $2::public.canal_telefone_engajamento
        ORDER BY telefone
        """,
        cnpj,
        CANAL_SMS,
    )
    return [_linha_para_contato(r) for r in rows]


async def listar_contatos_sms_com_fallback(
    executor: _Executor,
    cnpj_basico: str,
    legado_contatos_sms: Any,
) -> list[dict[str, Any]]:
    contatos = await listar_contatos_sms(executor, cnpj_basico)
    if contatos:
        return contatos
    return parse_contatos_json(legado_contatos_sms)


async def listar_contatos_sms_por_cnpjs(
    executor: _Executor,
    cnpjs: list[str],
) -> dict[str, list[dict[str, Any]]]:
    chaves = [(c or "").strip() for c in cnpjs if (c or "").strip()]
    if not chaves:
        return {}
    rows = await executor.fetch(
        f"""
        SELECT cnpj_basico, telefone, status, atualizado_em
        FROM {_tabela()}
        WHERE canal = $1::public.canal_telefone_engajamento
          AND cnpj_basico = ANY($2::text[])
        ORDER BY cnpj_basico, telefone
        """,
        CANAL_SMS,
        chaves,
    )
    out: dict[str, list[dict[str, Any]]] = {c: [] for c in chaves}
    for row in rows:
        cnpj = str(row["cnpj_basico"])
        out.setdefault(cnpj, []).append(_linha_para_contato(row))
    return out


async def telefone_sms_existe(
    executor: _Executor,
    cnpj_basico: str,
    telefone: str,
) -> bool:
    cnpj = (cnpj_basico or "").strip()
    tel = normalizar_telefone(telefone)
    if not cnpj or not tel:
        return False
    val = await executor.fetchval(
        f"""
        SELECT 1
        FROM {_tabela()}
        WHERE cnpj_basico = $1
          AND telefone = $2
          AND canal = $3::public.canal_telefone_engajamento
        LIMIT 1
        """,
        cnpj,
        tel,
        CANAL_SMS,
    )
    return val is not None


async def upsert_status_sms(
    executor: _Executor,
    *,
    cnpj_basico: str,
    telefone: str,
    status: str,
    atualizado_em: datetime | None = None,
) -> None:
    cnpj = (cnpj_basico or "").strip()
    tel = normalizar_telefone(telefone)
    if not cnpj or not tel:
        return
    ts = atualizado_em or datetime.now(UTC)
    await executor.execute(
        f"""
        INSERT INTO {_tabela()} (cnpj_basico, telefone, canal, status, atualizado_em)
        VALUES ($1, $2, $3::public.canal_telefone_engajamento, $4, $5)
        ON CONFLICT (cnpj_basico, telefone, canal) DO UPDATE SET
            status = EXCLUDED.status,
            atualizado_em = EXCLUDED.atualizado_em
        """,
        cnpj,
        tel,
        CANAL_SMS,
        status,
        ts,
    )


async def fundir_telefones_sms_novos(
    executor: _Executor,
    *,
    cnpj_basico: str,
    novos: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Acrescenta telefones novos na tabela; preserva estados já gravados."""
    cnpj = (cnpj_basico or "").strip()
    if not cnpj:
        return []
    existentes = await listar_contatos_sms(executor, cnpj)
    merged = fundir_lista_contatos_sms(existentes, novos)
    existentes_keys = {normalizar_telefone(str(c.get("endereco") or "")) for c in existentes}
    for contato in novos:
        tel = normalizar_telefone(str(contato.get("endereco") or ""))
        if not tel or tel in existentes_keys:
            continue
        estado = (str(contato.get("estado") or "").strip().lower()) or EngajamentoSmsEstado.ATIVO.value
        atualizado_em = _parse_atualizado_em(contato.get("ultima_atualizacao_em"))
        await upsert_status_sms(
            executor,
            cnpj_basico=cnpj,
            telefone=tel,
            status=estado,
            atualizado_em=atualizado_em,
        )
        existentes_keys.add(tel)
    return await listar_contatos_sms(executor, cnpj) or merged


async def garantir_telefone_sms_ativo(
    executor: _Executor,
    *,
    cnpj_basico: str,
    telefone: str,
    now_iso: str | None = None,
) -> None:
    tel = normalizar_telefone(telefone)
    if not tel:
        return
    if await telefone_sms_existe(executor, cnpj_basico, tel):
        return
    await upsert_status_sms(
        executor,
        cnpj_basico=cnpj_basico,
        telefone=tel,
        status=EngajamentoSmsEstado.ATIVO.value,
        atualizado_em=_parse_atualizado_em(now_iso or agora_iso()),
    )

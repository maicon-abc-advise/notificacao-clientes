"""Atualização de ``engajamento_fornecedores``: contatos em JSON + colunas agregadas por canal."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import asyncpg

from app.config.postgres_identificadores import obter_identificadores_postgres
from app.reenvio.servicos.engajamento_contatos import (
    agora_iso,
    fundir_lista_contatos_email,
    fundir_lista_contatos_sms,
    merge_contato,
    merge_contato_sms,
    normalizar_email,
    normalizar_telefone,
    parse_contatos_json,
    rollup_engajamento_email,
    rollup_engajamento_sms,
)
from app.reenvio.servicos.engajamento_estado import EngajamentoEmailEstado, EngajamentoSmsEstado

_log = logging.getLogger(__name__)

_SET_ULTIMO_EMAIL = frozenset(
    {
        EngajamentoEmailEstado.EMAIL_ENVIADO_API.value,
    }
)
_SET_ULTIMO_SMS = frozenset(
    {
        EngajamentoSmsEstado.SMS_ENVIADO_API.value,
    }
)


def parse_fornecedor_id(val: str | None) -> uuid.UUID | None:
    if not val or not str(val).strip():
        return None
    try:
        return uuid.UUID(str(val).strip())
    except ValueError:
        return None


def _as_jsonb_param(lista: list[dict[str, Any]]) -> str:
    return json.dumps(lista, ensure_ascii=False)


async def tocar_engajamento_email(
    pool: asyncpg.Pool,
    fornecedor_id: uuid.UUID | None,
    cnpj_basico: str | None,
    estado: EngajamentoEmailEstado,
    *,
    endereco: str | None = None,
) -> None:
    cnpj_b = (cnpj_basico or "").strip()
    if not cnpj_b:
        return
    est = estado.value
    p = obter_identificadores_postgres()
    te = p.qual("engajamento_fornecedores")
    now = agora_iso()
    end_in = normalizar_email(endereco) if endereco else ""

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                f"""
                INSERT INTO {te} (cnpj_basico, fornecedor_id)
                VALUES ($1, $2)
                ON CONFLICT (cnpj_basico) DO NOTHING
                """,
                cnpj_b,
                fornecedor_id,
            )
            row = await conn.fetchrow(
                f"""
                SELECT contatos_email, contatos_sms, ultimo_envio_email_endereco, ultimo_envio_sms_endereco
                FROM {te}
                WHERE cnpj_basico = $1
                FOR UPDATE
                """,
                cnpj_b,
            )
            contatos_e = parse_contatos_json(row["contatos_email"]) if row else []
            contatos_s = parse_contatos_json(row["contatos_sms"]) if row else []
            ultimo_e = (row["ultimo_envio_email_endereco"] or None) if row else None
            ultimo_s = (row["ultimo_envio_sms_endereco"] or None) if row else None

            alvo = end_in or (normalizar_email(ultimo_e) if ultimo_e else "")
            if not alvo:
                _log.warning(
                    "tocar_engajamento_email sem endereco e sem ultimo_envio_email_endereco cnpj_basico=%s estado=%s",
                    cnpj_b,
                    est,
                )
                return

            merge_contato(contatos_e, alvo, est, now_iso=now)
            if est in _SET_ULTIMO_EMAIL:
                ultimo_e = alvo

            agg_e = rollup_engajamento_email(contatos_e, ultimo_e).value
            agg_s = rollup_engajamento_sms(contatos_s, ultimo_s).value

            await conn.execute(
                f"""
                INSERT INTO {te} (
                    cnpj_basico, fornecedor_id,
                    contatos_email, contatos_sms,
                    engajamento_email, engajamento_sms,
                    engajamento_email_atualizado_em, engajamento_sms_atualizado_em,
                    engajamento_atualizado_em,
                    ultimo_envio_email_endereco, ultimo_envio_sms_endereco
                )
                VALUES (
                    $1, $2,
                    $3::jsonb, $4::jsonb,
                    $5, $6,
                    now(), now(), now(),
                    $7, $8
                )
                ON CONFLICT (cnpj_basico) DO UPDATE SET
                    fornecedor_id = COALESCE(EXCLUDED.fornecedor_id, {te}.fornecedor_id),
                    contatos_email = EXCLUDED.contatos_email,
                    contatos_sms = EXCLUDED.contatos_sms,
                    engajamento_email = EXCLUDED.engajamento_email,
                    engajamento_sms = EXCLUDED.engajamento_sms,
                    engajamento_email_atualizado_em = now(),
                    engajamento_sms_atualizado_em = now(),
                    engajamento_atualizado_em = now(),
                    ultimo_envio_email_endereco = EXCLUDED.ultimo_envio_email_endereco,
                    ultimo_envio_sms_endereco = EXCLUDED.ultimo_envio_sms_endereco
                """,
                cnpj_b,
                fornecedor_id,
                _as_jsonb_param(contatos_e),
                _as_jsonb_param(contatos_s),
                agg_e,
                agg_s,
                ultimo_e,
                ultimo_s,
            )
    _log.debug("Engajamento e-mail cnpj_basico=%s endereco=%s estado=%s agg=%s", cnpj_b, alvo, est, agg_e)


async def tocar_engajamento_sms(
    pool: asyncpg.Pool,
    fornecedor_id: uuid.UUID | None,
    cnpj_basico: str | None,
    estado: EngajamentoSmsEstado,
    *,
    endereco: str | None = None,
) -> None:
    cnpj_b = (cnpj_basico or "").strip()
    if not cnpj_b:
        return
    est = estado.value
    p = obter_identificadores_postgres()
    te = p.qual("engajamento_fornecedores")
    now = agora_iso()
    end_in = normalizar_telefone(endereco) if endereco else ""

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                f"""
                INSERT INTO {te} (cnpj_basico, fornecedor_id)
                VALUES ($1, $2)
                ON CONFLICT (cnpj_basico) DO NOTHING
                """,
                cnpj_b,
                fornecedor_id,
            )
            row = await conn.fetchrow(
                f"""
                SELECT contatos_email, contatos_sms, ultimo_envio_email_endereco, ultimo_envio_sms_endereco
                FROM {te}
                WHERE cnpj_basico = $1
                FOR UPDATE
                """,
                cnpj_b,
            )
            contatos_e = parse_contatos_json(row["contatos_email"]) if row else []
            contatos_s = parse_contatos_json(row["contatos_sms"]) if row else []
            ultimo_e = (row["ultimo_envio_email_endereco"] or None) if row else None
            ultimo_s = (row["ultimo_envio_sms_endereco"] or None) if row else None

            alvo = end_in or normalizar_telefone(ultimo_s or "")
            if not alvo:
                _log.warning(
                    "tocar_engajamento_sms sem endereco e sem ultimo_envio_sms_endereco cnpj_basico=%s estado=%s",
                    cnpj_b,
                    est,
                )
                return

            merge_contato_sms(contatos_s, alvo, est, now_iso=now)
            if est in _SET_ULTIMO_SMS:
                ultimo_s = alvo

            agg_e = rollup_engajamento_email(contatos_e, ultimo_e).value
            agg_s = rollup_engajamento_sms(contatos_s, ultimo_s).value

            await conn.execute(
                f"""
                INSERT INTO {te} (
                    cnpj_basico, fornecedor_id,
                    contatos_email, contatos_sms,
                    engajamento_email, engajamento_sms,
                    engajamento_email_atualizado_em, engajamento_sms_atualizado_em,
                    engajamento_atualizado_em,
                    ultimo_envio_email_endereco, ultimo_envio_sms_endereco
                )
                VALUES (
                    $1, $2,
                    $3::jsonb, $4::jsonb,
                    $5, $6,
                    now(), now(), now(),
                    $7, $8
                )
                ON CONFLICT (cnpj_basico) DO UPDATE SET
                    fornecedor_id = COALESCE(EXCLUDED.fornecedor_id, {te}.fornecedor_id),
                    contatos_email = EXCLUDED.contatos_email,
                    contatos_sms = EXCLUDED.contatos_sms,
                    engajamento_email = EXCLUDED.engajamento_email,
                    engajamento_sms = EXCLUDED.engajamento_sms,
                    engajamento_email_atualizado_em = now(),
                    engajamento_sms_atualizado_em = now(),
                    engajamento_atualizado_em = now(),
                    ultimo_envio_email_endereco = EXCLUDED.ultimo_envio_email_endereco,
                    ultimo_envio_sms_endereco = EXCLUDED.ultimo_envio_sms_endereco
                """,
                cnpj_b,
                fornecedor_id,
                _as_jsonb_param(contatos_e),
                _as_jsonb_param(contatos_s),
                agg_e,
                agg_s,
                ultimo_e,
                ultimo_s,
            )
    _log.debug("Engajamento SMS cnpj_basico=%s endereco=%s estado=%s agg=%s", cnpj_b, alvo, est, agg_s)


async def persistir_contatos_iniciais_engajamento(
    pool: asyncpg.Pool,
    *,
    cnpj_basico: str,
    fornecedor_id: uuid.UUID | None,
    contatos_email: list[dict[str, Any]],
    contatos_sms: list[dict[str, Any]],
) -> None:
    """Mescla listas novas (payload / company_profile) com o que já está no banco; não apaga canal com lista vazia."""
    cnpj_b = (cnpj_basico or "").strip()
    if not cnpj_b:
        return
    p = obter_identificadores_postgres()
    te = p.qual("engajamento_fornecedores")

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                f"""
                INSERT INTO {te} (cnpj_basico, fornecedor_id)
                VALUES ($1, $2)
                ON CONFLICT (cnpj_basico) DO NOTHING
                """,
                cnpj_b,
                fornecedor_id,
            )
            row = await conn.fetchrow(
                f"""
                SELECT contatos_email, contatos_sms, ultimo_envio_email_endereco, ultimo_envio_sms_endereco
                FROM {te}
                WHERE cnpj_basico = $1
                FOR UPDATE
                """,
                cnpj_b,
            )
            if row is None:
                return
            exist_e = parse_contatos_json(row["contatos_email"])
            exist_s = parse_contatos_json(row["contatos_sms"])
            merged_e = fundir_lista_contatos_email(exist_e, contatos_email)
            merged_s = fundir_lista_contatos_sms(exist_s, contatos_sms)
            ultimo_e = (row["ultimo_envio_email_endereco"] or None) or (
                normalizar_email(str(merged_e[0].get("endereco") or "")) if merged_e else None
            )
            ultimo_s = (row["ultimo_envio_sms_endereco"] or None) or (
                normalizar_telefone(str(merged_s[0].get("endereco") or "")) if merged_s else None
            )
            agg_e = rollup_engajamento_email(merged_e, ultimo_e).value
            agg_s = rollup_engajamento_sms(merged_s, ultimo_s).value
            await conn.execute(
                f"""
                UPDATE {te} SET
                    fornecedor_id = COALESCE($2, {te}.fornecedor_id),
                    contatos_email = $3::jsonb,
                    contatos_sms = $4::jsonb,
                    engajamento_email = $5,
                    engajamento_sms = $6,
                    engajamento_email_atualizado_em = now(),
                    engajamento_sms_atualizado_em = now(),
                    engajamento_atualizado_em = now(),
                    ultimo_envio_email_endereco = $7,
                    ultimo_envio_sms_endereco = $8
                WHERE cnpj_basico = $1
                """,
                cnpj_b,
                fornecedor_id,
                _as_jsonb_param(merged_e),
                _as_jsonb_param(merged_s),
                agg_e,
                agg_s,
                ultimo_e,
                ultimo_s,
            )


async def garantir_enderecos_no_engajamento(
    pool: asyncpg.Pool,
    *,
    cnpj_basico: str,
    fornecedor_id: uuid.UUID | None,
    email_opcional: str | None,
    telefone_opcional: str | None,
) -> None:
    """Inclui e-mail/telefone do payload nas listas (estado ativo) se ainda não existirem."""
    cnpj_b = (cnpj_basico or "").strip()
    if not cnpj_b:
        return
    p = obter_identificadores_postgres()
    te = p.qual("engajamento_fornecedores")
    now = agora_iso()
    ne = normalizar_email(email_opcional)
    nt = normalizar_telefone(telefone_opcional or "")

    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                f"""
                SELECT contatos_email, contatos_sms, ultimo_envio_email_endereco, ultimo_envio_sms_endereco
                FROM {te}
                WHERE cnpj_basico = $1
                FOR UPDATE
                """,
                cnpj_b,
            )
            if row is None:
                return
            contatos_e = parse_contatos_json(row["contatos_email"])
            contatos_s = parse_contatos_json(row["contatos_sms"])
            ultimo_e = row["ultimo_envio_email_endereco"] or None
            ultimo_s = row["ultimo_envio_sms_endereco"] or None
            if ne:
                merge_contato(contatos_e, ne, EngajamentoEmailEstado.ATIVO.value, now_iso=now)
            if nt:
                merge_contato_sms(contatos_s, nt, EngajamentoSmsEstado.ATIVO.value, now_iso=now)
            agg_e = rollup_engajamento_email(contatos_e, ultimo_e).value
            agg_s = rollup_engajamento_sms(contatos_s, ultimo_s).value
            await conn.execute(
                f"""
                UPDATE {te} SET
                    contatos_email = $2::jsonb,
                    contatos_sms = $3::jsonb,
                    engajamento_email = $4,
                    engajamento_sms = $5,
                    engajamento_email_atualizado_em = now(),
                    engajamento_sms_atualizado_em = now(),
                    engajamento_atualizado_em = now()
                WHERE cnpj_basico = $1
                """,
                cnpj_b,
                _as_jsonb_param(contatos_e),
                _as_jsonb_param(contatos_s),
                agg_e,
                agg_s,
            )


async def recalcular_agregados_engajamento(
    pool: asyncpg.Pool,
    *,
    cnpj_basico: str,
    fornecedor_id: uuid.UUID | None = None,
) -> None:
    """Recalcula só colunas agregadas a partir das listas e últimos envios (sem mudar contatos)."""
    cnpj_b = (cnpj_basico or "").strip()
    if not cnpj_b:
        return
    p = obter_identificadores_postgres()
    te = p.qual("engajamento_fornecedores")
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                f"""
                SELECT contatos_email, contatos_sms, ultimo_envio_email_endereco, ultimo_envio_sms_endereco
                FROM {te}
                WHERE cnpj_basico = $1
                FOR UPDATE
                """,
                cnpj_b,
            )
            if row is None:
                return
            contatos_e = parse_contatos_json(row["contatos_email"])
            contatos_s = parse_contatos_json(row["contatos_sms"])
            ultimo_e = row["ultimo_envio_email_endereco"] or None
            ultimo_s = row["ultimo_envio_sms_endereco"] or None
            agg_e = rollup_engajamento_email(contatos_e, ultimo_e).value
            agg_s = rollup_engajamento_sms(contatos_s, ultimo_s).value
            await conn.execute(
                f"""
                UPDATE {te} SET
                    engajamento_email = $2,
                    engajamento_sms = $3,
                    engajamento_email_atualizado_em = now(),
                    engajamento_sms_atualizado_em = now(),
                    engajamento_atualizado_em = now(),
                    fornecedor_id = COALESCE($4, {te}.fornecedor_id)
                WHERE cnpj_basico = $1
                """,
                cnpj_b,
                agg_e,
                agg_s,
                fornecedor_id,
            )

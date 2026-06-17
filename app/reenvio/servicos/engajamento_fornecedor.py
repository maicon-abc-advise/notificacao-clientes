"""Atualização de ``engajamento_fornecedores``: e-mail em JSON; SMS em ``telefone_engajamento``."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import asyncpg

from app.config.postgres_identificadores import obter_identificadores_postgres
from app.reenvio.repositorios.postgres_telefone_engajamento import (
    fundir_telefones_sms_novos,
    garantir_telefone_sms_ativo,
    listar_contatos_sms,
    listar_contatos_sms_com_fallback,
    telefone_sms_existe,
    upsert_status_sms,
)
from app.reenvio.servicos.engajamento_contatos import (
    agora_iso,
    contatos_incluem_email,
    fundir_lista_contatos_email,
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


async def _carregar_contatos_sms_transacao(
    conn: asyncpg.Connection,
    cnpj_basico: str,
    legado_contatos_sms: Any,
) -> list[dict[str, Any]]:
    return await listar_contatos_sms_com_fallback(conn, cnpj_basico, legado_contatos_sms)


async def exigir_destinatario_no_engajamento_email(
    pool: asyncpg.Pool,
    *,
    cnpj_basico: str,
    destinatario: str,
) -> None:
    """Garante que o e-mail já existe em ``contatos_email`` (mensageria não popula lista)."""
    cnpj_b = (cnpj_basico or "").strip()
    if not cnpj_b:
        raise ValueError("cnpj_basico é obrigatório para validar o envio.")
    p = obter_identificadores_postgres()
    te = p.qual("engajamento_fornecedores")
    row = await pool.fetchrow(
        f"SELECT contatos_email FROM {te} WHERE cnpj_basico = $1",
        cnpj_b,
    )
    if row is None:
        raise ValueError(
            "Não há engajamento para este CNPJ; a orquestração deve preparar os contatos antes do envio."
        )
    contatos = parse_contatos_json(row["contatos_email"])
    if not contatos_incluem_email(contatos, destinatario):
        raise ValueError("Destinatário não consta nos contatos de engajamento deste fornecedor.")


async def exigir_destinatario_no_engajamento_sms(
    pool: asyncpg.Pool,
    *,
    cnpj_basico: str,
    destinatario: str,
) -> None:
    cnpj_b = (cnpj_basico or "").strip()
    if not cnpj_b:
        raise ValueError("cnpj_basico é obrigatório para validar o envio.")
    p = obter_identificadores_postgres()
    te = p.qual("engajamento_fornecedores")
    row = await pool.fetchrow(
        f"SELECT 1 FROM {te} WHERE cnpj_basico = $1",
        cnpj_b,
    )
    if row is None:
        raise ValueError(
            "Não há engajamento para este CNPJ; a orquestração deve preparar os contatos antes do envio."
        )
    if not await telefone_sms_existe(pool, cnpj_b, destinatario):
        raise ValueError("Destinatário não consta nos contatos de engajamento deste fornecedor.")


async def tocar_engajamento_email(
    pool: asyncpg.Pool,
    fornecedor_id: uuid.UUID | None,
    cnpj_basico: str | None,
    estado: EngajamentoEmailEstado,
    *,
    endereco: str | None = None,
    somente_endereco_existente: bool = False,
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
            if not somente_endereco_existente:
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
            if row is None and somente_endereco_existente:
                _log.debug(
                    "tocar_engajamento_email somente_existente: sem linha cnpj_basico=%s estado=%s",
                    cnpj_b,
                    est,
                )
                return
            contatos_e = parse_contatos_json(row["contatos_email"]) if row else []
            contatos_s = await _carregar_contatos_sms_transacao(
                conn,
                cnpj_b,
                row["contatos_sms"] if row else None,
            )
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

            permitir_novo = not somente_endereco_existente
            if not merge_contato(contatos_e, alvo, est, now_iso=now, permitir_novo=permitir_novo):
                _log.debug(
                    "tocar_engajamento_email somente_existente: endereco não estava na lista cnpj=%s alvo=%s",
                    cnpj_b,
                    alvo,
                )
                return
            if est in _SET_ULTIMO_EMAIL:
                ultimo_e = alvo

            agg_e = rollup_engajamento_email(contatos_e, ultimo_e).value
            agg_s = rollup_engajamento_sms(contatos_s, ultimo_s).value

            if somente_endereco_existente:
                await conn.execute(
                    f"""
                    UPDATE {te} SET
                        fornecedor_id = COALESCE($2, {te}.fornecedor_id),
                        contatos_email = $3::jsonb,
                        engajamento_email = $4,
                        engajamento_sms = $5,
                        engajamento_email_atualizado_em = now(),
                        engajamento_sms_atualizado_em = now(),
                        engajamento_atualizado_em = now(),
                        ultimo_envio_email_endereco = $6,
                        ultimo_envio_sms_endereco = $7
                    WHERE cnpj_basico = $1
                    """,
                    cnpj_b,
                    fornecedor_id,
                    _as_jsonb_param(contatos_e),
                    agg_e,
                    agg_s,
                    ultimo_e,
                    ultimo_s,
                )
            else:
                await conn.execute(
                    f"""
                    INSERT INTO {te} (
                        cnpj_basico, fornecedor_id,
                        contatos_email,
                        engajamento_email, engajamento_sms,
                        engajamento_email_atualizado_em, engajamento_sms_atualizado_em,
                        engajamento_atualizado_em,
                        ultimo_envio_email_endereco, ultimo_envio_sms_endereco
                    )
                    VALUES (
                        $1, $2,
                        $3::jsonb,
                        $4, $5,
                        now(), now(), now(),
                        $6, $7
                    )
                    ON CONFLICT (cnpj_basico) DO UPDATE SET
                        fornecedor_id = COALESCE(EXCLUDED.fornecedor_id, {te}.fornecedor_id),
                        contatos_email = EXCLUDED.contatos_email,
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
    somente_endereco_existente: bool = False,
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
            if not somente_endereco_existente:
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
            if row is None and somente_endereco_existente:
                _log.debug(
                    "tocar_engajamento_sms somente_existente: sem linha cnpj_basico=%s estado=%s",
                    cnpj_b,
                    est,
                )
                return
            contatos_e = parse_contatos_json(row["contatos_email"]) if row else []
            contatos_s = await _carregar_contatos_sms_transacao(
                conn,
                cnpj_b,
                row["contatos_sms"] if row else None,
            )
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

            permitir_novo = not somente_endereco_existente
            if not merge_contato_sms(contatos_s, alvo, est, now_iso=now, permitir_novo=permitir_novo):
                _log.debug(
                    "tocar_engajamento_sms somente_existente: endereco não estava na lista cnpj=%s alvo=%s",
                    cnpj_b,
                    alvo,
                )
                return

            await upsert_status_sms(
                conn,
                cnpj_basico=cnpj_b,
                telefone=alvo,
                status=est,
                atualizado_em=_parse_atualizado_em(now),
            )
            contatos_s = await listar_contatos_sms(conn, cnpj_b)

            if est in _SET_ULTIMO_SMS:
                ultimo_s = alvo

            agg_e = rollup_engajamento_email(contatos_e, ultimo_e).value
            agg_s = rollup_engajamento_sms(contatos_s, ultimo_s).value

            await conn.execute(
                f"""
                UPDATE {te} SET
                    fornecedor_id = COALESCE($2, {te}.fornecedor_id),
                    engajamento_email = $3,
                    engajamento_sms = $4,
                    engajamento_email_atualizado_em = now(),
                    engajamento_sms_atualizado_em = now(),
                    engajamento_atualizado_em = now(),
                    ultimo_envio_email_endereco = $5,
                    ultimo_envio_sms_endereco = $6
                WHERE cnpj_basico = $1
                """,
                cnpj_b,
                fornecedor_id,
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
    """Mescla contatos novos (payload / company_profile); SMS em ``telefone_engajamento``."""
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
                SELECT contatos_email, ultimo_envio_email_endereco, ultimo_envio_sms_endereco
                FROM {te}
                WHERE cnpj_basico = $1
                FOR UPDATE
                """,
                cnpj_b,
            )
            if row is None:
                return
            exist_e = parse_contatos_json(row["contatos_email"])
            merged_e = fundir_lista_contatos_email(exist_e, contatos_email)
            merged_s = await fundir_telefones_sms_novos(
                conn,
                cnpj_basico=cnpj_b,
                novos=contatos_sms,
            )
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
                    engajamento_email = $4,
                    engajamento_sms = $5,
                    engajamento_email_atualizado_em = now(),
                    engajamento_sms_atualizado_em = now(),
                    engajamento_atualizado_em = now(),
                    ultimo_envio_email_endereco = $6,
                    ultimo_envio_sms_endereco = $7
                WHERE cnpj_basico = $1
                """,
                cnpj_b,
                fornecedor_id,
                _as_jsonb_param(merged_e),
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
            ultimo_e = row["ultimo_envio_email_endereco"] or None
            ultimo_s = row["ultimo_envio_sms_endereco"] or None
            if ne:
                merge_contato(contatos_e, ne, EngajamentoEmailEstado.ATIVO.value, now_iso=now)
            if nt:
                await garantir_telefone_sms_ativo(
                    conn,
                    cnpj_basico=cnpj_b,
                    telefone=nt,
                    now_iso=now,
                )
            contatos_s = await _carregar_contatos_sms_transacao(conn, cnpj_b, row["contatos_sms"])
            agg_e = rollup_engajamento_email(contatos_e, ultimo_e).value
            agg_s = rollup_engajamento_sms(contatos_s, ultimo_s).value
            await conn.execute(
                f"""
                UPDATE {te} SET
                    contatos_email = $2::jsonb,
                    engajamento_email = $3,
                    engajamento_sms = $4,
                    engajamento_email_atualizado_em = now(),
                    engajamento_sms_atualizado_em = now(),
                    engajamento_atualizado_em = now()
                WHERE cnpj_basico = $1
                """,
                cnpj_b,
                _as_jsonb_param(contatos_e),
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
            contatos_s = await _carregar_contatos_sms_transacao(conn, cnpj_b, row["contatos_sms"])
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

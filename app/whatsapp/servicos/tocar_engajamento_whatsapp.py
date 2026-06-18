"""Sync ``telefone_engajamento`` (canal whatsapp) + rollup ``engajamento_whatsapp``."""

from __future__ import annotations

import enum
import logging
import uuid
from datetime import UTC, datetime

import asyncpg

from app.config.postgres_identificadores import obter_identificadores_postgres
from app.reenvio.repositorios.postgres_telefone_engajamento import (
    CANAL_WHATSAPP,
    promover_ou_gravar_whatsapp,
)
from app.reenvio.servicos.engajamento_contatos import agora_iso, normalizar_telefone

_log = logging.getLogger(__name__)


class WhatsappEngajamentoEstado(enum.StrEnum):
    WHATSAPP_PENDENTE_FILA = "whatsapp_pendente_fila"
    WHATSAPP_VALIDO = "whatsapp_valido"
    WHATSAPP_INVALIDO = "whatsapp_invalido"
    WHATSAPP_CONTATADO = "whatsapp_contatado"
    WHATSAPP_CONCLUIDO_SUCESSO = "whatsapp_concluido_sucesso"
    WHATSAPP_CONCLUIDO_FALHA = "whatsapp_concluido_falha"


def _rollup_whatsapp(estado: str) -> str:
    if estado in (
        WhatsappEngajamentoEstado.WHATSAPP_CONCLUIDO_FALHA.value,
        WhatsappEngajamentoEstado.WHATSAPP_INVALIDO.value,
    ):
        return "inativo"
    if estado in (
        WhatsappEngajamentoEstado.WHATSAPP_CONTATADO.value,
        WhatsappEngajamentoEstado.WHATSAPP_PENDENTE_FILA.value,
        WhatsappEngajamentoEstado.WHATSAPP_VALIDO.value,
    ):
        return "em_analise"
    return "ativo"


def _parse_ts(val: str) -> datetime:
    try:
        dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        return datetime.now(UTC)


async def tocar_engajamento_whatsapp(
    pool: asyncpg.Pool,
    fornecedor_id: uuid.UUID | None,
    cnpj_basico: str | None,
    estado: WhatsappEngajamentoEstado,
    *,
    telefone: str | None = None,
) -> None:
    cnpj_b = (cnpj_basico or "").strip()
    if not cnpj_b:
        return
    tel = normalizar_telefone(telefone) if telefone else ""
    if not tel:
        _log.warning("tocar_engajamento_whatsapp sem telefone cnpj=%s estado=%s", cnpj_b, estado.value)
        return

    p = obter_identificadores_postgres()
    te = p.qual("engajamento_fornecedores")
    cf = p.col_fornecedor_id
    now = agora_iso()
    ts = _parse_ts(now)
    agg = _rollup_whatsapp(estado.value)

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                f"""
                INSERT INTO {te} (cnpj_basico, {cf})
                VALUES ($1, $2)
                ON CONFLICT (cnpj_basico) DO NOTHING
                """,
                cnpj_b,
                fornecedor_id,
            )
            await promover_ou_gravar_whatsapp(
                conn,
                cnpj_basico=cnpj_b,
                telefone=tel,
                status=estado.value,
                atualizado_em=ts,
            )
            await conn.execute(
                f"""
                UPDATE {te} SET
                    engajamento_whatsapp = $2,
                    ultimo_envio_whatsapp_telefone = $3,
                    engajamento_whatsapp_atualizado_em = now(),
                    engajamento_atualizado_em = now(),
                    {cf} = COALESCE($4, {te}.{cf})
                WHERE cnpj_basico = $1
                """,
                cnpj_b,
                agg,
                tel,
                fornecedor_id,
            )
    _log.debug("Engajamento WhatsApp cnpj=%s tel=%s estado=%s agg=%s", cnpj_b, tel, estado.value, agg)

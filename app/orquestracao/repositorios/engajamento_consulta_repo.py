from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

import asyncpg

from app.config.postgres_identificadores import obter_identificadores_postgres
from app.reenvio.servicos.engajamento_estado import EngajamentoEmailEstado, EngajamentoSmsEstado


@dataclass(frozen=True, slots=True)
class SnapshotEngajamentoOrquestracao:
    engajamento_email: str
    engajamento_sms: str
    recebe_email: bool
    ultimo_lembrete_limite_semanal_em: datetime | None


async def carregar_para_fornecedor(
    pool: asyncpg.Pool,
    fornecedor_id: uuid.UUID,
) -> SnapshotEngajamentoOrquestracao:
    p = obter_identificadores_postgres()
    te = p.qual("engajamento_fornecedores")
    cf = p.col_fornecedor_id
    row = await pool.fetchrow(
        f"""
        SELECT engajamento_email, engajamento_sms, recebe_email, ultimo_lembrete_limite_semanal_em
        FROM {te}
        WHERE {cf} = $1
        """,
        fornecedor_id,
    )
    if row is None:
        return SnapshotEngajamentoOrquestracao(
            EngajamentoEmailEstado.ATIVO.value,
            EngajamentoSmsEstado.ATIVO.value,
            True,
            None,
        )
    return SnapshotEngajamentoOrquestracao(
        row["engajamento_email"],
        row["engajamento_sms"],
        row["recebe_email"],
        row["ultimo_lembrete_limite_semanal_em"],
    )


async def registrar_lembrete_creditos_semanal(pool: asyncpg.Pool, fornecedor_id: uuid.UUID) -> None:
    p = obter_identificadores_postgres()
    te = p.qual("engajamento_fornecedores")
    cf = p.col_fornecedor_id
    await pool.execute(
        f"""
        INSERT INTO {te} ({cf}, ultimo_lembrete_limite_semanal_em)
        VALUES ($1, now())
        ON CONFLICT ({cf}) DO UPDATE SET
            ultimo_lembrete_limite_semanal_em = now()
        """,
        fornecedor_id,
    )

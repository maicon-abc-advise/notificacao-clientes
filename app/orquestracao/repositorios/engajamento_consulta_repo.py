from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

import asyncpg

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
    row = await pool.fetchrow(
        """
        SELECT engajamento_email, engajamento_sms, recebe_email, ultimo_lembrete_limite_semanal_em
        FROM public.engajamento_fornecedores
        WHERE fornecedor_id = $1
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
    await pool.execute(
        """
        INSERT INTO public.engajamento_fornecedores (fornecedor_id, ultimo_lembrete_limite_semanal_em)
        VALUES ($1, now())
        ON CONFLICT (fornecedor_id) DO UPDATE SET
            ultimo_lembrete_limite_semanal_em = now()
        """,
        fornecedor_id,
    )

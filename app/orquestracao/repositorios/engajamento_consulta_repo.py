from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import asyncpg

from app.config.postgres_identificadores import obter_identificadores_postgres
from app.reenvio.servicos.engajamento_contatos import parse_contatos_json
from app.reenvio.servicos.engajamento_estado import EngajamentoCanalAgregado


@dataclass(frozen=True, slots=True)
class SnapshotEngajamentoOrquestracao:
    engajamento_email: str
    engajamento_sms: str
    contatos_email: list[dict[str, Any]]
    contatos_sms: list[dict[str, Any]]
    ultimo_envio_email_endereco: str | None
    ultimo_envio_sms_endereco: str | None
    ultimo_lembrete_limite_semanal_em: datetime | None

    def tem_contatos_carregados(self) -> bool:
        return bool(self.contatos_email) or bool(self.contatos_sms)


def _snapshot_padrao_sem_linha() -> SnapshotEngajamentoOrquestracao:
    return SnapshotEngajamentoOrquestracao(
        engajamento_email=EngajamentoCanalAgregado.INATIVO.value,
        engajamento_sms=EngajamentoCanalAgregado.INATIVO.value,
        contatos_email=[],
        contatos_sms=[],
        ultimo_envio_email_endereco=None,
        ultimo_envio_sms_endereco=None,
        ultimo_lembrete_limite_semanal_em=None,
    )


async def garantir_linha_engajamento(
    pool: asyncpg.Pool,
    *,
    cnpj_basico: str,
    cnpj: str | None,
    fornecedor_id: uuid.UUID | None,
    nome_fantasia: str | None = None,
) -> None:
    p = obter_identificadores_postgres()
    te = p.qual("engajamento_fornecedores")
    await pool.execute(
        f"""
        INSERT INTO {te} (cnpj_basico, cnpj, fornecedor_id, nome_fantasia)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (cnpj_basico) DO UPDATE SET
            cnpj = COALESCE(EXCLUDED.cnpj, {te}.cnpj),
            fornecedor_id = COALESCE(EXCLUDED.fornecedor_id, {te}.fornecedor_id),
            nome_fantasia = CASE
                WHEN EXCLUDED.nome_fantasia IS NOT NULL AND btrim(EXCLUDED.nome_fantasia) <> '' THEN btrim(EXCLUDED.nome_fantasia)
                ELSE {te}.nome_fantasia
            END
        """,
        cnpj_basico,
        cnpj,
        fornecedor_id,
        nome_fantasia,
    )


async def incrementar_aparicao_busca(
    pool: asyncpg.Pool,
    *,
    cnpj_basico: str,
    nome_fantasia: str | None = None,
) -> None:
    p = obter_identificadores_postgres()
    te = p.qual("engajamento_fornecedores")
    await pool.execute(
        f"""
        INSERT INTO {te} (cnpj_basico, aparicoes_busca, nome_fantasia)
        VALUES ($1, 1, $2)
        ON CONFLICT (cnpj_basico) DO UPDATE SET
            aparicoes_busca = {te}.aparicoes_busca + 1,
            engajamento_atualizado_em = now(),
            nome_fantasia = CASE
                WHEN EXCLUDED.nome_fantasia IS NOT NULL AND btrim(EXCLUDED.nome_fantasia) <> '' THEN btrim(EXCLUDED.nome_fantasia)
                ELSE {te}.nome_fantasia
            END
        """,
        cnpj_basico,
        nome_fantasia,
    )


async def carregar_por_cnpj_basico(
    pool: asyncpg.Pool,
    cnpj_basico: str,
) -> SnapshotEngajamentoOrquestracao:
    p = obter_identificadores_postgres()
    te = p.qual("engajamento_fornecedores")
    row = await pool.fetchrow(
        f"""
        SELECT engajamento_email, engajamento_sms,
               contatos_email, contatos_sms,
               ultimo_envio_email_endereco, ultimo_envio_sms_endereco,
               ultimo_lembrete_limite_semanal_em
        FROM {te}
        WHERE cnpj_basico = $1
        """,
        cnpj_basico,
    )
    if row is None:
        return _snapshot_padrao_sem_linha()
    return SnapshotEngajamentoOrquestracao(
        row["engajamento_email"],
        row["engajamento_sms"],
        parse_contatos_json(row["contatos_email"]),
        parse_contatos_json(row["contatos_sms"]),
        row["ultimo_envio_email_endereco"],
        row["ultimo_envio_sms_endereco"],
        row["ultimo_lembrete_limite_semanal_em"],
    )


async def registrar_lembrete_creditos_semanal(pool: asyncpg.Pool, cnpj_basico: str) -> None:
    p = obter_identificadores_postgres()
    te = p.qual("engajamento_fornecedores")
    await pool.execute(
        f"""
        INSERT INTO {te} (cnpj_basico, ultimo_lembrete_limite_semanal_em)
        VALUES ($1, now())
        ON CONFLICT (cnpj_basico) DO UPDATE SET
            ultimo_lembrete_limite_semanal_em = now()
        """,
        cnpj_basico,
    )

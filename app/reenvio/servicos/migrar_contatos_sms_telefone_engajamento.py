"""Migra ``contatos_sms`` (JSON) de ``engajamento_fornecedores`` para ``telefone_engajamento``."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import asyncpg

from app.config.postgres_identificadores import obter_identificadores_postgres
from app.reenvio.servicos.engajamento_contatos import (
    normalizar_telefone,
    parse_contatos_json,
)
from app.reenvio.servicos.engajamento_estado import EngajamentoSmsEstado

_log = logging.getLogger(__name__)

CANAL_SMS = "sms"
_MIN_TELEFONE_LEN = 10


def parse_atualizado_em_contato(val: Any) -> datetime:
    """Converte ``ultima_atualizacao_em`` do JSON para ``timestamptz``."""
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


def linhas_migracao_sms_de_fornecedor(
    cnpj_basico: str,
    contatos_sms: Any,
) -> tuple[list[dict[str, Any]], int, int]:
    """
    Extrai linhas para upsert em ``telefone_engajamento`` a partir do JSON legado.

    Retorna ``(linhas, ignorados_sem_telefone, ignorados_telefone_invalido)``.
    """
    cnpj = (cnpj_basico or "").strip()
    contatos = parse_contatos_json(contatos_sms)
    linhas: list[dict[str, Any]] = []
    ignorados_sem = 0
    ignorados_invalido = 0

    for contato in contatos:
        telefone = normalizar_telefone(str(contato.get("endereco") or ""))
        if not telefone:
            ignorados_sem += 1
            continue
        if len(telefone) < _MIN_TELEFONE_LEN:
            ignorados_invalido += 1
            continue

        status = (str(contato.get("estado") or "").strip().lower()) or EngajamentoSmsEstado.ATIVO.value
        atualizado_em = parse_atualizado_em_contato(contato.get("ultima_atualizacao_em"))
        linhas.append(
            {
                "cnpj_basico": cnpj,
                "telefone": telefone,
                "canal": CANAL_SMS,
                "status": status,
                "atualizado_em": atualizado_em,
            }
        )

    return linhas, ignorados_sem, ignorados_invalido


async def executar_migrar_contatos_sms_para_telefone_engajamento(
    pool: asyncpg.Pool,
    *,
    cnpj_basico: str | None = None,
    limite: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Lê ``engajamento_fornecedores.contatos_sms`` e grava em ``telefone_engajamento`` (canal sms).

    Idempotente: ``ON CONFLICT`` atualiza ``status`` e ``atualizado_em``.
    """
    pg = obter_identificadores_postgres()
    t_eng = pg.qual("engajamento_fornecedores")
    t_tel = pg.qual("telefone_engajamento")

    cnpj_filtro = (cnpj_basico or "").strip() or None
    limite_efetivo: int | None = None
    if limite is not None:
        limite_efetivo = max(1, min(limite, 50_000))

    params: list[Any] = []
    where = "WHERE contatos_sms IS NOT NULL AND contatos_sms::text NOT IN ('[]', 'null')"
    if cnpj_filtro:
        params.append(cnpj_filtro)
        where += f" AND cnpj_basico = ${len(params)}"

    sql_select = f"""
        SELECT cnpj_basico, contatos_sms
        FROM {t_eng}
        {where}
        ORDER BY cnpj_basico
    """
    if limite_efetivo is not None:
        params.append(limite_efetivo)
        sql_select += f" LIMIT ${len(params)}"

    sql_upsert = f"""
        INSERT INTO {t_tel} (cnpj_basico, telefone, canal, status, atualizado_em)
        VALUES ($1, $2, $3::public.canal_telefone_engajamento, $4, $5)
        ON CONFLICT (cnpj_basico, telefone, canal) DO UPDATE SET
            status = EXCLUDED.status,
            atualizado_em = EXCLUDED.atualizado_em
    """

    fornecedores_lidos = 0
    contatos_lidos = 0
    linhas_gravadas = 0
    ignorados_sem_telefone = 0
    ignorados_telefone_invalido = 0
    fornecedores_sem_contatos = 0

    async with pool.acquire() as conn:
        rows = await conn.fetch(sql_select, *params)

        async with conn.transaction():
            for row in rows:
                fornecedores_lidos += 1
                cnpj = str(row["cnpj_basico"]).strip()
                contatos = parse_contatos_json(row["contatos_sms"])
                if not contatos:
                    fornecedores_sem_contatos += 1
                    continue

                contatos_lidos += len(contatos)
                linhas, ign_sem, ign_inv = linhas_migracao_sms_de_fornecedor(cnpj, contatos)
                ignorados_sem_telefone += ign_sem
                ignorados_telefone_invalido += ign_inv

                for linha in linhas:
                    if dry_run:
                        linhas_gravadas += 1
                        continue
                    await conn.execute(
                        sql_upsert,
                        linha["cnpj_basico"],
                        linha["telefone"],
                        linha["canal"],
                        linha["status"],
                        linha["atualizado_em"],
                    )
                    linhas_gravadas += 1

    resultado = {
        "dry_run": dry_run,
        "cnpj_basico_filtro": cnpj_filtro,
        "limite": limite_efetivo,
        "fornecedores_lidos": fornecedores_lidos,
        "fornecedores_sem_contatos": fornecedores_sem_contatos,
        "contatos_lidos": contatos_lidos,
        "linhas_gravadas": linhas_gravadas,
        "ignorados_sem_telefone": ignorados_sem_telefone,
        "ignorados_telefone_invalido": ignorados_telefone_invalido,
    }
    _log.info("Migração telefone_engajamento concluída: %s", resultado)
    return resultado

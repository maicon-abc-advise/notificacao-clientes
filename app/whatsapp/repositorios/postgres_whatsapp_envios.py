"""Persistência de ``whatsapp_envios`` — alinhado ao schema Supabase ``busca_fornecedor``."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import asyncpg

from app.config.postgres_identificadores import obter_identificadores_postgres

# Schema Supabase (produção): cnpj_empresa, id bigint, etapas text — sem criado_em / motivo_falha / fornecedor_id.
_COL_CNPJ = "cnpj_empresa"

RESULTADOS_ETAPA = frozenset({"sucesso", "falha", "ignorado", "inconclusivo"})


def _tabela() -> str:
    return obter_identificadores_postgres().qual("whatsapp_envios")


def _select_listagem() -> str:
    return f"""
        w.id,
        w.updated_at,
        w.status,
        w.etapa1,
        w.etapa2,
        w.etapa3,
        w.whatsapp_status,
        w.{_COL_CNPJ} AS cnpj_basico,
        w.{_COL_CNPJ},
        w.numero_telefone
    """


def _parse_id(envio_id: uuid.UUID | str | int) -> int:
    return int(envio_id)


def cnpj_de_row(row: asyncpg.Record | dict[str, Any]) -> str:
    return str(row.get("cnpj_basico") or row.get("cnpj_empresa") or "").strip()


async def buscar_por_id(pool: asyncpg.Pool, envio_id: uuid.UUID | str | int) -> asyncpg.Record | None:
    return await pool.fetchrow(
        f"SELECT * FROM {_tabela()} WHERE id = $1 LIMIT 1",
        _parse_id(envio_id),
    )


async def buscar_por_cnpj_telefone(
    pool: asyncpg.Pool,
    *,
    cnpj_basico: str,
    numero_telefone: str,
) -> asyncpg.Record | None:
    return await pool.fetchrow(
        f"""
        SELECT * FROM {_tabela()}
        WHERE {_COL_CNPJ} = $1 AND numero_telefone = $2
        LIMIT 1
        """,
        cnpj_basico.strip(),
        numero_telefone.strip(),
    )


async def buscar_ultimo_por_cnpj(pool: asyncpg.Pool, cnpj_basico: str) -> asyncpg.Record | None:
    return await pool.fetchrow(
        f"""
        SELECT * FROM {_tabela()}
        WHERE {_COL_CNPJ} = $1
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        cnpj_basico.strip(),
    )


async def inserir_se_ausente(
    pool: asyncpg.Pool,
    *,
    cnpj_basico: str,
    numero_telefone: str,
    fornecedor_id: uuid.UUID | None = None,
) -> tuple[asyncpg.Record | None, bool]:
    _ = fornecedor_id
    cnpj = cnpj_basico.strip()
    tel = numero_telefone.strip()
    # Produção (Supabase): UNIQUE em cnpj_empresa (`idx_whatsapp_envios_cnpj`) — 1 linha por CNPJ.
    row = await pool.fetchrow(
        f"""
        INSERT INTO {_tabela()} ({_COL_CNPJ}, numero_telefone, status, whatsapp_status)
        VALUES ($1, $2, 'pendente', 'nao_verificado')
        ON CONFLICT ({_COL_CNPJ}) DO NOTHING
        RETURNING *
        """,
        cnpj,
        tel,
    )
    if row is not None:
        return row, True
    existente = await buscar_por_cnpj_telefone(pool, cnpj_basico=cnpj, numero_telefone=tel)
    if existente is None:
        existente = await buscar_ultimo_por_cnpj(pool, cnpj)
    return existente, False


async def atualizar_status(
    pool: asyncpg.Pool,
    envio_id: uuid.UUID | str | int,
    *,
    status: str | None = None,
    whatsapp_status: str | None = None,
    motivo_falha: str | None = None,
) -> asyncpg.Record | None:
    _ = motivo_falha
    sets: list[str] = ["updated_at = now()"]
    params: list[Any] = [_parse_id(envio_id)]
    idx = 2
    if status is not None:
        sets.append(f"status = ${idx}")
        params.append(status)
        idx += 1
    if whatsapp_status is not None:
        sets.append(f"whatsapp_status = ${idx}")
        params.append(whatsapp_status)
        idx += 1
    return await pool.fetchrow(
        f"UPDATE {_tabela()} SET {', '.join(sets)} WHERE id = $1 RETURNING *",
        *params,
    )


def _contar_etapas_preenchidas(row: asyncpg.Record | dict[str, Any]) -> int:
    etapas = [row["etapa1"], row["etapa2"], row["etapa3"]]
    return sum(1 for e in etapas if e is not None and str(e).strip())


async def registrar_resultado_etapa(
    pool: asyncpg.Pool,
    envio_id: uuid.UUID | str | int,
    resultado: str,
    *,
    max_etapas: int = 3,
) -> asyncpg.Record | None:
    """Grava resultado da tentativa atual em ``etapa1``/``etapa2``/``etapa3`` e atualiza o funil."""
    if resultado not in RESULTADOS_ETAPA:
        raise ValueError(f"resultado de etapa inválido: {resultado!r}")
    row = await buscar_por_id(pool, envio_id)
    if not row:
        return None
    n = _contar_etapas_preenchidas(row)

    if resultado in ("sucesso", "falha"):
        status = "concluido_sucesso" if resultado == "sucesso" else "concluido_falha"
        if n >= max_etapas:
            return await atualizar_status(pool, envio_id, status=status)
        col = f"etapa{n + 1}"
        return await pool.fetchrow(
            f"""
            UPDATE {_tabela()}
            SET {col} = $2, updated_at = now(), status = $3
            WHERE id = $1
            RETURNING *
            """,
            _parse_id(envio_id),
            resultado,
            status,
        )

    if n >= max_etapas:
        return await atualizar_status(pool, envio_id, status="concluido_falha")
    col = f"etapa{n + 1}"
    novo_n = n + 1
    novo_status = "concluido_falha" if novo_n >= max_etapas else "pendente"
    return await pool.fetchrow(
        f"""
        UPDATE {_tabela()}
        SET {col} = $2, updated_at = now(), status = $3
        WHERE id = $1
        RETURNING *
        """,
        _parse_id(envio_id),
        resultado,
        novo_status,
    )


async def incrementar_etapa_falha(
    pool: asyncpg.Pool,
    envio_id: uuid.UUID | str | int,
    *,
    max_falhas: int = 3,
) -> asyncpg.Record | None:
    """Compatibilidade: inconclusivo legado (timestamps antigos)."""
    return await registrar_resultado_etapa(
        pool, envio_id, "inconclusivo", max_etapas=max_falhas
    )


async def listar_pendentes_para_envio(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    return await pool.fetch(
        f"""
        SELECT w.*,
               (SELECT COUNT(*)::int FROM {_tabela()} w2
                WHERE w2.numero_telefone = w.numero_telefone
                  AND w2.status = 'contatado'
                  AND w2.id <> w.id) AS outros_contatados_mesmo_tel
        FROM {_tabela()} w
        WHERE w.status = 'pendente'
        ORDER BY w.updated_at ASC
        """,
    )


async def listar_contatados_para_atualizacao(
    pool: asyncpg.Pool,
    *,
    max_falhas: int = 3,
) -> list[asyncpg.Record]:
    _ = max_falhas
    return await pool.fetch(
        f"""
        SELECT w.*
        FROM {_tabela()} w
        WHERE w.status = 'contatado'
        ORDER BY w.updated_at ASC
        """,
    )


async def listar_candidatos_rotina(pool: asyncpg.Pool, *, max_falhas: int = 3) -> list[asyncpg.Record]:
    pendentes = await listar_pendentes_para_envio(pool)
    contatados = await listar_contatados_para_atualizacao(pool, max_falhas=max_falhas)
    return list(pendentes) + list(contatados)


async def contar_por_status(pool: asyncpg.Pool, *, where_extra: str = "", params: list[Any] | None = None) -> dict[str, int]:
    p = params or []
    rows = await pool.fetch(
        f"""
        SELECT status, COUNT(*)::int AS n
        FROM {_tabela()}
        {f'WHERE {where_extra}' if where_extra else ''}
        GROUP BY status
        """,
        *p,
    )
    out = {"pendente": 0, "contatado": 0, "concluido_sucesso": 0, "concluido_falha": 0}
    for r in rows:
        st = r["status"]
        if st is None:
            continue
        out[str(st)] = int(r["n"])
    return out


async def contar_whatsapp_status(pool: asyncpg.Pool) -> dict[str, int]:
    rows = await pool.fetch(
        f"""
        SELECT whatsapp_status, COUNT(*)::int AS n
        FROM {_tabela()}
        GROUP BY whatsapp_status
        """,
    )
    return {str(r["whatsapp_status"]): int(r["n"]) for r in rows if r["whatsapp_status"] is not None}


async def listar_paginado(
    pool: asyncpg.Pool,
    *,
    offset: int,
    limit: int,
    status: str | None = None,
    whatsapp_status: str | None = None,
    cnpj_basico: str | None = None,
) -> tuple[list[asyncpg.Record], int]:
    filtros: list[str] = []
    params: list[Any] = []
    idx = 1
    if status:
        filtros.append(f"w.status = ${idx}")
        params.append(status)
        idx += 1
    if whatsapp_status:
        filtros.append(f"w.whatsapp_status = ${idx}")
        params.append(whatsapp_status)
        idx += 1
    if cnpj_basico:
        filtros.append(f"w.{_COL_CNPJ} ILIKE ${idx}")
        params.append(f"%{cnpj_basico.strip()}%")
        idx += 1
    where = f"WHERE {' AND '.join(filtros)}" if filtros else ""
    total = int(await pool.fetchval(f"SELECT COUNT(*) FROM {_tabela()} w {where}", *params) or 0)
    params.extend([limit, offset])
    rows = await pool.fetch(
        f"""
        SELECT {_select_listagem()}
        FROM {_tabela()} w
        {where}
        ORDER BY w.updated_at DESC
        LIMIT ${idx} OFFSET ${idx + 1}
        """,
        *params,
    )
    return rows, total


async def salvar_execucao_rotina(
    pool: asyncpg.Pool,
    *,
    resultado: dict[str, Any],
    iniciado_em: datetime,
    finalizado_em: datetime,
) -> int | uuid.UUID:
    tbl = obter_identificadores_postgres().qual("whatsapp_rotina_execucoes")
    try:
        row = await pool.fetchrow(
            f"""
            INSERT INTO {tbl} (resultado, iniciado_em, finalizado_em)
            VALUES ($1::jsonb, $2, $3)
            RETURNING id
            """,
            json.dumps(resultado),
            iniciado_em if iniciado_em.tzinfo else iniciado_em.replace(tzinfo=UTC),
            finalizado_em if finalizado_em.tzinfo else finalizado_em.replace(tzinfo=UTC),
        )
        return row["id"]
    except asyncpg.UndefinedTableError:
        return 0


async def listar_execucoes_rotina(pool: asyncpg.Pool, *, limit: int = 20) -> list[asyncpg.Record]:
    tbl = obter_identificadores_postgres().qual("whatsapp_rotina_execucoes")
    try:
        return await pool.fetch(
            f"""
            SELECT id, iniciado_em, finalizado_em, criado_em,
                   (resultado->>'processed')::int AS processados,
                   jsonb_array_length(COALESCE(resultado->'actions', '[]'::jsonb)) AS acoes
            FROM {tbl}
            ORDER BY iniciado_em DESC
            LIMIT $1
            """,
            limit,
        )
    except asyncpg.UndefinedTableError:
        return []


async def buscar_execucao_rotina(pool: asyncpg.Pool, execucao_id: uuid.UUID | str | int) -> asyncpg.Record | None:
    tbl = obter_identificadores_postgres().qual("whatsapp_rotina_execucoes")
    try:
        return await pool.fetchrow(f"SELECT * FROM {tbl} WHERE id = $1", _parse_id(execucao_id))
    except asyncpg.UndefinedTableError:
        return None

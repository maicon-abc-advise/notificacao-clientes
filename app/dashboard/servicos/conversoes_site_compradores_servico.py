"""Métricas e listagem: shortlinks do site (sem cadastro) → comprador cadastrado."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import asyncpg

from app.config.postgres_identificadores import obter_identificadores_postgres


def _filtro_shortlinks_site_sem_cadastro(*, alias_sl: str = "sl", alias_c: str = "c") -> str:
    return f"""
        LOWER(TRIM(COALESCE({alias_c}.origem, ''))) = 'site'
        AND {alias_sl}.comprador_id IS NULL
    """


def _filtro_consulta_convertida(*, alias_c: str = "c", tabela_usuario: str) -> str:
    return f"""
        {alias_c}.comprador IS NOT NULL
        AND EXISTS (
            SELECT 1
            FROM {tabela_usuario} uc_chk
            WHERE uc_chk.id = {alias_c}.comprador
        )
    """


def _append_periodo_shortlink(
    filtros: list[str],
    params: list[Any],
    periodo: tuple[datetime, datetime] | None,
    *,
    alias: str = "sl",
) -> None:
    if not periodo:
        return
    params.append(periodo[0])
    p_ini = f"${len(params)}"
    params.append(periodo[1])
    p_fim = f"${len(params)}"
    filtros.append(f"{alias}.created_at >= {p_ini} AND {alias}.created_at <= {p_fim}")


async def contar_metricas_conversoes_site(
    pool: asyncpg.Pool,
    periodo: tuple[datetime, datetime] | None,
) -> tuple[int, int]:
    p = obter_identificadores_postgres()
    t_sl = p.qual("consulta_shortlinks")
    t_c = p.qual("consultas")
    t_uc = p.qual("usuario_comprador")

    filtros = [_filtro_shortlinks_site_sem_cadastro()]
    params: list[Any] = []
    _append_periodo_shortlink(filtros, params, periodo)
    where_sql = " AND ".join(filtros)
    convertido_sql = _filtro_consulta_convertida(tabela_usuario=t_uc)

    row = await pool.fetchrow(
        f"""
        SELECT
            COUNT(*)::bigint AS shortlinks_site,
            COUNT(*) FILTER (WHERE {convertido_sql})::bigint AS conversoes
        FROM {t_sl} sl
        INNER JOIN {t_c} c ON c.id = sl.consulta_id
        WHERE {where_sql}
        """,
        *params,
    )
    shortlinks = int((row["shortlinks_site"] if row else 0) or 0)
    conversoes = int((row["conversoes"] if row else 0) or 0)
    return shortlinks, conversoes


async def listar_conversoes_site_compradores(
    pool: asyncpg.Pool,
    *,
    page: int,
    page_size: int,
    periodo: tuple[datetime, datetime] | None,
    apenas_convertidos: bool | None,
) -> tuple[list[dict[str, Any]], int]:
    p = obter_identificadores_postgres()
    t_sl = p.qual("consulta_shortlinks")
    t_c = p.qual("consultas")
    t_uc = p.qual("usuario_comprador")

    filtros = [_filtro_shortlinks_site_sem_cadastro()]
    params: list[Any] = []
    _append_periodo_shortlink(filtros, params, periodo)

    convertido_sql = _filtro_consulta_convertida(tabela_usuario=t_uc)
    if apenas_convertidos is True:
        filtros.append(convertido_sql)
    elif apenas_convertidos is False:
        filtros.append(f"NOT ({convertido_sql})")

    where_sql = " AND ".join(filtros)
    offset = (page - 1) * page_size

    total = int(
        await pool.fetchval(
            f"""
            SELECT COUNT(*)::bigint
            FROM {t_sl} sl
            INNER JOIN {t_c} c ON c.id = sl.consulta_id
            WHERE {where_sql}
            """,
            *params,
        )
        or 0
    )

    rows = await pool.fetch(
        f"""
        SELECT
            sl.id AS shortlink_id,
            sl.code AS shortlink_code,
            sl.created_at AS shortlink_criado_em,
            sl.view_count,
            c.id AS consulta_id,
            c.comprador AS comprador_id,
            uc.nome AS comprador_nome,
            uc.empresa_nome,
            uc.created_at AS comprador_cadastrado_em,
            ({convertido_sql}) AS converteu
        FROM {t_sl} sl
        INNER JOIN {t_c} c ON c.id = sl.consulta_id
        LEFT JOIN {t_uc} uc ON uc.id = c.comprador
        WHERE {where_sql}
        ORDER BY sl.created_at DESC NULLS LAST, sl.code ASC
        LIMIT {page_size} OFFSET {offset}
        """,
        *params,
    )

    itens: list[dict[str, Any]] = []
    for row in rows:
        converteu = bool(row["converteu"])
        itens.append(
            {
                "shortlink_id": str(row["shortlink_id"]),
                "shortlink_code": row["shortlink_code"],
                "shortlink_criado_em": row["shortlink_criado_em"],
                "view_count": row["view_count"],
                "consulta_id": str(row["consulta_id"]),
                "comprador_id": str(row["comprador_id"]) if row["comprador_id"] else None,
                "comprador_nome": row["comprador_nome"],
                "empresa_nome": row["empresa_nome"],
                "comprador_cadastrado_em": row["comprador_cadastrado_em"],
                "converteu": converteu,
                "estado_exibicao": {
                    "rotulo": "Convertido" if converteu else "Pendente",
                    "cor": "success" if converteu else "info",
                },
            }
        )
    return itens, total

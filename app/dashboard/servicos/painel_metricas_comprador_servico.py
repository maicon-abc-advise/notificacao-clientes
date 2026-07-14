"""Painel de métricas do comprador (gráficos estilo home): site + e-mail."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any

import asyncpg

from app.config.postgres_identificadores import obter_identificadores_postgres
from app.dashboard.servicos.conversoes_site_compradores_servico import (
    _filtro_consulta_convertida,
    _filtro_shortlinks_site_sem_cadastro,
)


def _serie_base(inicio: date, fim: date) -> dict[str, int]:
    out: dict[str, int] = {}
    cur = inicio
    from datetime import timedelta

    while cur <= fim:
        out[cur.isoformat()] = 0
        cur += timedelta(days=1)
    return out


def _serie_resposta(inicio: date, fim: date, valores: dict[str, int]) -> list[dict[str, Any]]:
    from datetime import timedelta

    pontos: list[dict[str, Any]] = []
    cur = inicio
    while cur <= fim:
        iso = cur.isoformat()
        pontos.append(
            {
                "data": iso,
                "rotulo": cur.strftime("%d/%m"),
                "valor": int(valores.get(iso) or 0),
            }
        )
        cur += timedelta(days=1)
    return pontos


def _taxa(parte: int, total: int) -> int:
    if total <= 0:
        return 0
    return int(round((parte / total) * 100))


def _linha(chave: str, rotulo: str, valor: int, base: int) -> dict[str, Any]:
    return {
        "chave": chave,
        "rotulo": rotulo,
        "valor": int(valor),
        "percentual": _taxa(int(valor), int(base)),
    }


def _painel(
    *,
    metrica_padrao: str,
    metricas: list[dict[str, Any]],
    series_por_metrica: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    return {
        "metrica_padrao": metrica_padrao,
        "metricas": metricas,
        "series_por_metrica": series_por_metrica,
    }


def _periodo_bounds(inicio: date, fim: date) -> tuple[datetime, datetime]:
    ini = datetime.combine(inicio, time.min, tzinfo=timezone.utc)
    fim_dt = datetime.combine(fim, time.max, tzinfo=timezone.utc)
    return ini, fim_dt


async def _preencher_serie(
    pool: asyncpg.Pool,
    *,
    sql: str,
    inicio: date,
    fim: date,
    params: list[Any],
) -> dict[str, int]:
    serie = _serie_base(inicio, fim)
    rows = await pool.fetch(sql, *params)
    for row in rows:
        ref = row["ref"]
        chave = ref.isoformat() if hasattr(ref, "isoformat") else str(ref)
        if chave in serie:
            serie[chave] = int(row["total"] or 0)
    return serie


async def _metricas_conversoes_site_periodo(
    pool: asyncpg.Pool,
    inicio: date,
    fim: date,
) -> dict[str, Any]:
    p = obter_identificadores_postgres()
    t_sl = p.qual("consulta_shortlinks")
    t_c = p.qual("consultas")
    t_uc = p.qual("usuario_comprador")
    ini, fim_dt = _periodo_bounds(inicio, fim)
    filtro_site = _filtro_shortlinks_site_sem_cadastro()
    convertido_sql = _filtro_consulta_convertida(tabela_usuario=t_uc)

    row = await pool.fetchrow(
        f"""
        SELECT
            COUNT(*)::bigint AS shortlinks,
            COUNT(*) FILTER (WHERE {convertido_sql})::bigint AS conversoes
        FROM {t_sl} sl
        INNER JOIN {t_c} c ON c.id = sl.consulta_id
        WHERE {filtro_site}
          AND sl.created_at >= $1 AND sl.created_at <= $2
        """,
        ini,
        fim_dt,
    )
    shortlinks = int((row["shortlinks"] if row else 0) or 0)
    conversoes = int((row["conversoes"] if row else 0) or 0)
    taxa = _taxa(conversoes, shortlinks)
    base = max(shortlinks, 1)

    serie_links = await _preencher_serie(
        pool,
        sql=f"""
            SELECT sl.created_at::date AS ref, COUNT(*)::bigint AS total
            FROM {t_sl} sl
            INNER JOIN {t_c} c ON c.id = sl.consulta_id
            WHERE {filtro_site}
              AND sl.created_at::date BETWEEN $1 AND $2
            GROUP BY 1
        """,
        inicio=inicio,
        fim=fim,
        params=[inicio, fim],
    )
    serie_conv = await _preencher_serie(
        pool,
        sql=f"""
            SELECT sl.created_at::date AS ref, COUNT(*)::bigint AS total
            FROM {t_sl} sl
            INNER JOIN {t_c} c ON c.id = sl.consulta_id
            WHERE {filtro_site}
              AND ({convertido_sql})
              AND sl.created_at::date BETWEEN $1 AND $2
            GROUP BY 1
        """,
        inicio=inicio,
        fim=fim,
        params=[inicio, fim],
    )
    # Taxa diária: % por dia (conversoes/links do dia)
    serie_taxa: dict[str, int] = _serie_base(inicio, fim)
    for dia, links in serie_links.items():
        serie_taxa[dia] = _taxa(serie_conv.get(dia, 0), links)

    return _painel(
        metrica_padrao="conversoes",
        metricas=[
            _linha("links", "Links criados", shortlinks, base),
            _linha("conversoes", "Conversões", conversoes, base),
            _linha("taxa", "Taxa de conversão (%)", taxa, 100),
        ],
        series_por_metrica={
            "links": _serie_resposta(inicio, fim, serie_links),
            "conversoes": _serie_resposta(inicio, fim, serie_conv),
            "taxa": _serie_resposta(inicio, fim, serie_taxa),
        },
    )


async def _metricas_conversoes_email_periodo(
    pool: asyncpg.Pool,
    inicio: date,
    fim: date,
) -> dict[str, Any]:
    """Funil de conversão de compradores contactados (engajamento_compradores)."""
    p = obter_identificadores_postgres()
    tc = p.qual("engajamento_compradores")
    ini, fim_dt = _periodo_bounds(inicio, fim)

    row = await pool.fetchrow(
        f"""
        SELECT
            COUNT(*)::bigint AS contactados,
            COUNT(*) FILTER (WHERE primeira_consulta_sem_cadastro = true)::bigint AS elegiveis,
            COUNT(*) FILTER (WHERE converteu = true)::bigint AS convertidos
        FROM {tc}
        WHERE criado_em >= $1 AND criado_em <= $2
        """,
        ini,
        fim_dt,
    )
    contactados = int((row["contactados"] if row else 0) or 0)
    elegiveis = int((row["elegiveis"] if row else 0) or 0)
    convertidos = int((row["convertidos"] if row else 0) or 0)
    pendentes = max(elegiveis - convertidos, 0)
    base = max(contactados, 1)
    taxa = _taxa(convertidos, max(elegiveis, 1) if elegiveis else contactados)

    serie_contactados = await _preencher_serie(
        pool,
        sql=f"""
            SELECT criado_em::date AS ref, COUNT(*)::bigint AS total
            FROM {tc}
            WHERE criado_em::date BETWEEN $1 AND $2
            GROUP BY 1
        """,
        inicio=inicio,
        fim=fim,
        params=[inicio, fim],
    )
    serie_elegiveis = await _preencher_serie(
        pool,
        sql=f"""
            SELECT criado_em::date AS ref, COUNT(*)::bigint AS total
            FROM {tc}
            WHERE primeira_consulta_sem_cadastro = true
              AND criado_em::date BETWEEN $1 AND $2
            GROUP BY 1
        """,
        inicio=inicio,
        fim=fim,
        params=[inicio, fim],
    )
    serie_convertidos = await _preencher_serie(
        pool,
        sql=f"""
            SELECT COALESCE(converteu_em, atualizado_em, criado_em)::date AS ref,
                   COUNT(*)::bigint AS total
            FROM {tc}
            WHERE converteu = true
              AND COALESCE(converteu_em, atualizado_em, criado_em)::date BETWEEN $1 AND $2
            GROUP BY 1
        """,
        inicio=inicio,
        fim=fim,
        params=[inicio, fim],
    )
    serie_pendentes = await _preencher_serie(
        pool,
        sql=f"""
            SELECT criado_em::date AS ref, COUNT(*)::bigint AS total
            FROM {tc}
            WHERE primeira_consulta_sem_cadastro = true
              AND converteu = false
              AND criado_em::date BETWEEN $1 AND $2
            GROUP BY 1
        """,
        inicio=inicio,
        fim=fim,
        params=[inicio, fim],
    )

    return _painel(
        metrica_padrao="convertidos",
        metricas=[
            _linha("contactados", "Contactados", contactados, base),
            _linha("elegiveis", "Elegíveis", elegiveis, base),
            _linha("convertidos", "Convertidos", convertidos, base),
            _linha("pendentes", "Pendentes", pendentes, base),
            _linha("taxa", "Taxa de conversão (%)", taxa, 100),
        ],
        series_por_metrica={
            "contactados": _serie_resposta(inicio, fim, serie_contactados),
            "elegiveis": _serie_resposta(inicio, fim, serie_elegiveis),
            "convertidos": _serie_resposta(inicio, fim, serie_convertidos),
            "pendentes": _serie_resposta(inicio, fim, serie_pendentes),
            "taxa": _serie_resposta(
                inicio,
                fim,
                {
                    dia: _taxa(serie_convertidos.get(dia, 0), max(serie_elegiveis.get(dia, 0), 1))
                    if serie_elegiveis.get(dia, 0) > 0
                    else _taxa(serie_convertidos.get(dia, 0), max(serie_contactados.get(dia, 0), 1))
                    for dia in serie_contactados
                },
            ),
        },
    )


async def montar_painel_metricas_comprador(
    pool: asyncpg.Pool,
    inicio: date,
    fim: date,
) -> dict[str, Any]:
    site = await _metricas_conversoes_site_periodo(pool, inicio, fim)
    email = await _metricas_conversoes_email_periodo(pool, inicio, fim)
    return {
        "periodo": {
            "data_inicio": inicio.isoformat(),
            "data_fim": fim.isoformat(),
            "total_dias": (fim - inicio).days + 1,
        },
        "painel": {
            "conversoes_site": site,
            "conversoes_email": email,
        },
    }

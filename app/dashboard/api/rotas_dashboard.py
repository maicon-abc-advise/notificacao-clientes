"""Endpoints de leitura para o dashboard (autenticação interna)."""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.config.postgres_identificadores import obter_identificadores_postgres
from app.dashboard.servicos.exibicao import (
    enriquecer_linha_postgres,
    enriquecer_redis_email_esperando,
    enriquecer_redis_email_pendente,
    enriquecer_redis_sms_esperando,
    enriquecer_redis_sms_pendente,
)
from app.dashboard.servicos.serializacao import decodificar_contexto_json_bruto, registo_para_json
from app.iam.rotas.dashboard_rotas import usuario_logado
from app.orquestracao.api.dependencias import PoolOrquestracao, RedisOrquestracao
from app.orquestracao.repositorios.redis_emails_pendentes_repo import KEY_INDEX as IDX_EMAIL_PEND
from app.orquestracao.repositorios.redis_emails_pendentes_repo import chave_hash as chave_email_pend
from app.reenvio.repositorios.redis_emails_esperando_confirmacao import KEY_SWEEP as IDX_EMAIL_CONF
from app.reenvio.repositorios.redis_emails_esperando_confirmacao import chave_hash as chave_email_conf
from app.reenvio.repositorios.redis_sms_esperando_confirmacao import KEY_SWEEP as IDX_SMS_CONF
from app.reenvio.repositorios.redis_sms_esperando_confirmacao import chave_hash as chave_sms_conf
from app.reenvio.repositorios.redis_sms_pendente import KEY_INDEX as IDX_SMS_PEND
from app.reenvio.repositorios.redis_sms_pendente import chave_hash as chave_sms_pend

router = APIRouter(
    prefix="/v1/interno/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(usuario_logado)],
)

PAGE_SIZE = 10


def _page_clamped(page: int) -> int:
    return max(1, page)


def _meta(total: int, page: int) -> dict[str, int]:
    return {
        "total": total,
        "page": page,
        "page_size": PAGE_SIZE,
        "total_pages": max(1, math.ceil(total / PAGE_SIZE)) if total else 1,
    }


def _h(raw: dict[Any, Any], key: str) -> str | None:
    """Lê campo de hash Redis com chaves/valores str ou bytes."""
    if not raw:
        return None
    for rk, rv in raw.items():
        ks = rk.decode() if isinstance(rk, bytes) else str(rk)
        if ks != key:
            continue
        if rv is None:
            return None
        if isinstance(rv, bytes):
            return rv.decode(errors="replace")
        return str(rv)
    return None


def _texto(v: str | None) -> str | None:
    s = (v or "").strip()
    return s or None


def _busca_cnpj(v: str | None) -> str | None:
    s = _texto(v)
    if not s:
        return None
    return f"%{s}%"


def _append_param(params: list[Any], value: Any) -> str:
    params.append(value)
    return f"${len(params)}"


def _normalizar_periodo(
    data_inicio: date | None,
    data_fim: date | None,
) -> tuple[date, date]:
    hoje = date.today()
    fim = data_fim or hoje
    inicio = data_inicio or (fim - timedelta(days=6))
    if data_inicio and not data_fim:
        fim = data_inicio + timedelta(days=6)
    if inicio > fim:
        raise HTTPException(status_code=400, detail="data_inicio não pode ser maior que data_fim")
    return inicio, fim


def _datas_periodo(inicio: date, fim: date) -> list[date]:
    dias = (fim - inicio).days
    return [inicio + timedelta(days=i) for i in range(dias + 1)]


def _serie_base(inicio: date, fim: date) -> dict[str, int]:
    return {dia.isoformat(): 0 for dia in _datas_periodo(inicio, fim)}


def _serie_resposta(inicio: date, fim: date, valores: dict[str, int]) -> list[dict[str, Any]]:
    pontos: list[dict[str, Any]] = []
    for dia in _datas_periodo(inicio, fim):
        iso = dia.isoformat()
        pontos.append(
            {
                "data": iso,
                "rotulo": dia.strftime("%d/%m"),
                "valor": int(valores.get(iso) or 0),
            }
        )
    return pontos


def _pagina_itens(itens: list[dict[str, Any]], page: int) -> tuple[list[dict[str, Any]], int]:
    total = len(itens)
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    return itens[start:end], total


def _segmento(rotulo: str, valor: int, cor: str) -> dict[str, Any]:
    return {"rotulo": rotulo, "valor": int(valor), "cor": cor}


def _cartao(
    chave: str,
    valor: int,
    legenda: str,
    *,
    total: int | None = None,
    segmentos: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {"chave": chave, "valor": int(valor), "legenda": legenda}
    if total is not None:
        out["total"] = int(total)
    if segmentos:
        out["segmentos"] = segmentos
    return out


def _taxa_percentual(parte: int, total: int) -> int:
    if total <= 0:
        return 0
    return int(round((parte / total) * 100))


async def _coluna_data_fornecedores(pool: PoolOrquestracao) -> str | None:
    p = obter_identificadores_postgres()
    tabela = p.nome_fisico_tabela("fornecedores")
    rows = await pool.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = $1
          AND table_name = $2
        """,
        p.schema,
        tabela,
    )
    existentes = {str(row["column_name"]) for row in rows}
    for candidata in ("created_at", "criado_em", "updated_at", "atualizado_em"):
        if candidata in existentes:
            return candidata
    return None


async def _serie_por_dia(
    pool: PoolOrquestracao,
    *,
    sql: str,
    inicio: date,
    fim: date,
    params: list[Any] | None = None,
) -> dict[str, int]:
    serie = _serie_base(inicio, fim)
    final_params: list[Any] = [inicio, fim]
    if params:
        final_params.extend(params)
    rows = await pool.fetch(sql, *final_params)
    for row in rows:
        ref = row["ref"]
        if hasattr(ref, "isoformat"):
            chave = ref.isoformat()
        else:
            chave = str(ref)
        serie[chave] = int(row["total"] or 0)
    return serie


async def _resumo_engajamento(pool: PoolOrquestracao) -> dict[str, int]:
    p = obter_identificadores_postgres()
    te = p.qual("engajamento_fornecedores")
    tf = p.qual("fornecedores")
    row = await pool.fetchrow(
        f"""
        SELECT
            COUNT(*) AS total_monitorados,
            COUNT(*) FILTER (
                WHERE jsonb_array_length(COALESCE(contatos_email, '[]'::jsonb)) > 0
            ) AS usuarios_com_email,
            COUNT(*) FILTER (
                WHERE jsonb_array_length(COALESCE(contatos_sms, '[]'::jsonb)) > 0
            ) AS usuarios_com_telefone,
            COUNT(*) FILTER (
                WHERE (
                    jsonb_array_length(COALESCE(contatos_email, '[]'::jsonb)) > 0
                    OR jsonb_array_length(COALESCE(contatos_sms, '[]'::jsonb)) > 0
                )
            ) AS usuarios_com_algum_contato,
            COUNT(*) FILTER (
                WHERE e.cadastrado_primeiro_contato = false
                  AND EXISTS (
                      SELECT 1
                      FROM {tf} AS f
                      WHERE f.cnpj_basico = e.cnpj_basico
                  )
            ) AS usuarios_convertidos
        FROM {te} AS e
        """,
    )
    return {
        "total_monitorados": int(row["total_monitorados"] or 0),
        "usuarios_com_email": int(row["usuarios_com_email"] or 0),
        "usuarios_com_telefone": int(row["usuarios_com_telefone"] or 0),
        "usuarios_com_algum_contato": int(row["usuarios_com_algum_contato"] or 0),
        "usuarios_convertidos": int(row["usuarios_convertidos"] or 0),
    }


async def _conversoes_por_canal(
    pool: PoolOrquestracao,
    *,
    inicio: date | None = None,
    fim: date | None = None,
) -> dict[str, int]:
    p = obter_identificadores_postgres()
    te = p.qual("engajamento_fornecedores")
    tf = p.qual("fornecedores")
    tem = p.qual("emails_enviados")
    tsm = p.qual("sms_enviados")
    coluna_data = await _coluna_data_fornecedores(pool)

    params: list[Any] = []
    where_extra = ""
    if coluna_data and inicio and fim:
        p_ini = _append_param(params, inicio)
        p_fim = _append_param(params, fim)
        where_extra = f" AND f.{coluna_data}::date BETWEEN {p_ini} AND {p_fim}"

    row = await pool.fetchrow(
        f"""
        WITH convertidos AS (
            SELECT
                e.cnpj_basico,
                EXISTS (
                    SELECT 1
                    FROM {tem} AS em
                    WHERE COALESCE(em.contexto->>'cnpj_basico', '') = e.cnpj_basico
                ) AS tem_email,
                EXISTS (
                    SELECT 1
                    FROM {tsm} AS sm
                    WHERE COALESCE(sm.contexto->>'cnpj_basico', '') = e.cnpj_basico
                ) AS tem_sms
            FROM {te} AS e
            INNER JOIN {tf} AS f ON f.cnpj_basico = e.cnpj_basico
            WHERE e.cadastrado_primeiro_contato = false
            {where_extra}
        )
        SELECT
            COUNT(*) FILTER (WHERE tem_email AND NOT tem_sms) AS so_email,
            COUNT(*) FILTER (WHERE tem_sms AND NOT tem_email) AS so_sms,
            COUNT(*) FILTER (WHERE tem_email AND tem_sms) AS ambos,
            COUNT(*) FILTER (WHERE NOT tem_email AND NOT tem_sms) AS sem_historico
        FROM convertidos
        """,
        *params,
    )
    return {
        "so_email": int(row["so_email"] or 0),
        "so_sms": int(row["so_sms"] or 0),
        "ambos": int(row["ambos"] or 0),
        "sem_historico": int(row["sem_historico"] or 0),
    }


def _normalizar_linha_postgres_mensagem(item: dict[str, Any], *, canal: str) -> dict[str, Any]:
    cnpj_ctx = item.pop("cnpj_basico_dashboard", None)
    if not item.get("cnpj_basico") and cnpj_ctx:
        item["cnpj_basico"] = cnpj_ctx
    return enriquecer_linha_postgres(item, canal=canal)


@router.get("/home/resumo")
async def resumo_home_dashboard(
    pool: PoolOrquestracao,
    data_inicio: date | None = None,
    data_fim: date | None = None,
) -> dict[str, Any]:
    inicio, fim = _normalizar_periodo(data_inicio, data_fim)
    p = obter_identificadores_postgres()
    te = p.qual("emails_enviados")
    ts = p.qual("sms_enviados")
    tf = p.qual("fornecedores")
    teg = p.qual("engajamento_fornecedores")

    total_emails = int(
        await pool.fetchval(
            f"""
            SELECT COUNT(*)
            FROM {te}
            WHERE criado_em::date BETWEEN $1 AND $2
            """,
            inicio,
            fim,
        )
        or 0
    )
    emails_lidos = int(
        await pool.fetchval(
            f"""
            SELECT COUNT(*)
            FROM {te}
            WHERE criado_em::date BETWEEN $1 AND $2
              AND status_ultimo IN ('lido', 'clicado')
            """,
            inicio,
            fim,
        )
        or 0
    )

    total_sms = int(
        await pool.fetchval(
            f"""
            SELECT COUNT(*)
            FROM {ts}
            WHERE criado_em::date BETWEEN $1 AND $2
            """,
            inicio,
            fim,
        )
        or 0
    )
    sms_entregues = int(
        await pool.fetchval(
            f"""
            SELECT COUNT(*)
            FROM {ts}
            WHERE criado_em::date BETWEEN $1 AND $2
              AND status_ultimo IN ('enviado', 'lido', 'clicado')
            """,
            inicio,
            fim,
        )
        or 0
    )

    resumo_eng = await _resumo_engajamento(pool)
    coluna_data_fornecedor = await _coluna_data_fornecedores(pool)

    convertidos_periodo = 0
    serie_convertidos = _serie_base(inicio, fim)
    if coluna_data_fornecedor:
        convertidos_periodo = int(
            await pool.fetchval(
                f"""
                SELECT COUNT(DISTINCT e.cnpj_basico)
                FROM {teg} AS e
                INNER JOIN {tf} AS f ON f.cnpj_basico = e.cnpj_basico
                WHERE e.cadastrado_primeiro_contato = false
                  AND f.{coluna_data_fornecedor}::date BETWEEN $1 AND $2
                """,
                inicio,
                fim,
            )
            or 0
        )
        serie_convertidos = await _serie_por_dia(
            pool,
            inicio=inicio,
            fim=fim,
            sql=f"""
                SELECT f.{coluna_data_fornecedor}::date AS ref, COUNT(DISTINCT e.cnpj_basico) AS total
                FROM {teg} AS e
                INNER JOIN {tf} AS f ON f.cnpj_basico = e.cnpj_basico
                WHERE e.cadastrado_primeiro_contato = false
                  AND f.{coluna_data_fornecedor}::date BETWEEN $1 AND $2
                GROUP BY 1
                ORDER BY 1
            """,
        )

    serie_emails = await _serie_por_dia(
        pool,
        inicio=inicio,
        fim=fim,
        sql=f"""
            SELECT criado_em::date AS ref, COUNT(*) AS total
            FROM {te}
            WHERE criado_em::date BETWEEN $1 AND $2
            GROUP BY 1
            ORDER BY 1
        """,
    )
    serie_sms = await _serie_por_dia(
        pool,
        inicio=inicio,
        fim=fim,
        sql=f"""
            SELECT criado_em::date AS ref, COUNT(*) AS total
            FROM {ts}
            WHERE criado_em::date BETWEEN $1 AND $2
            GROUP BY 1
            ORDER BY 1
        """,
    )

    emails_nao_lidos = max(total_emails - emails_lidos, 0)
    sms_pendentes = max(total_sms - sms_entregues, 0)
    canais = await _conversoes_por_canal(pool, inicio=inicio, fim=fim)
    total_canais = sum(canais.values())

    return {
        "periodo": {
            "data_inicio": inicio.isoformat(),
            "data_fim": fim.isoformat(),
            "total_dias": len(_datas_periodo(inicio, fim)),
        },
        "cartoes": [
            _cartao("emails_periodo", total_emails, "E-mails no período"),
            _cartao("sms_periodo", total_sms, "SMS no período"),
            _cartao("convertidos_periodo", convertidos_periodo, "Usuários convertidos"),
            _cartao("taxa_leitura", _taxa_percentual(emails_lidos, total_emails), "Taxa de leitura (%)"),
            _cartao("usuarios_monitorados", resumo_eng["total_monitorados"], "Usuários monitorados"),
        ],
        "series": {
            "emails": _serie_resposta(inicio, fim, serie_emails),
            "sms": _serie_resposta(inicio, fim, serie_sms),
            "convertidos": _serie_resposta(inicio, fim, serie_convertidos),
        },
        "distribuicoes": [
            {
                "chave": "emails_leitura",
                "titulo": "E-mails lidos vs não lidos",
                "valor": emails_lidos,
                "total": total_emails,
                "segmentos": [
                    _segmento("Lidos", emails_lidos, "success"),
                    _segmento("Não lidos", emails_nao_lidos, "neutral"),
                ],
            },
            {
                "chave": "sms_situacao",
                "titulo": "SMS entregues vs pendentes",
                "valor": sms_entregues,
                "total": total_sms,
                "segmentos": [
                    _segmento("Entregues", sms_entregues, "success"),
                    _segmento("Pendentes", sms_pendentes, "warning"),
                ],
            },
            {
                "chave": "conversoes_canal",
                "titulo": "Conversões por histórico de canal",
                "valor": total_canais,
                "total": total_canais,
                "segmentos": [
                    _segmento("Só e-mail", canais["so_email"], "info"),
                    _segmento("Só SMS", canais["so_sms"], "warning"),
                    _segmento("Ambos", canais["ambos"], "success"),
                    _segmento("Sem histórico", canais["sem_historico"], "neutral"),
                ],
            },
        ],
        "resumo_engajamento": resumo_eng,
    }


@router.get("/emails/metricas")
async def metricas_emails(
    pool: PoolOrquestracao,
    redis: RedisOrquestracao,
) -> dict[str, Any]:
    p = obter_identificadores_postgres()
    te = p.qual("emails_enviados")
    total = int(await pool.fetchval(f"SELECT COUNT(*) FROM {te}") or 0)
    falhas = int(
        await pool.fetchval(
            f"SELECT COUNT(*) FROM {te} WHERE status_ultimo = 'falha_definitiva'",
        )
        or 0,
    )
    lidos = int(
        await pool.fetchval(
            f"SELECT COUNT(*) FROM {te} WHERE status_ultimo = 'lido'",
        )
        or 0,
    )
    clicados = int(
        await pool.fetchval(
            f"SELECT COUNT(*) FROM {te} WHERE status_ultimo = 'clicado'",
        )
        or 0,
    )
    pendentes = int(await redis.zcard(IDX_EMAIL_PEND) or 0)
    esperando = int(await redis.zcard(IDX_EMAIL_CONF) or 0)
    return {
        "emails_enviados_total": total,
        "emails_pendentes_pre_envio": pendentes,
        "emails_esperando_confirmacao": esperando,
        "emails_falha_definitiva": falhas,
        "emails_lidos": lidos,
        "emails_clicados": clicados,
        "cartoes": [
            _cartao("enviados", total, "E-mails registados"),
            _cartao("pendentes", pendentes, "Na fila pré-envio"),
            _cartao("recusados", falhas, "Falha definitiva"),
            _cartao("esperando_feedback", esperando, "Esperando confirmação"),
            _cartao("abertos", lidos, "E-mails lidos"),
            _cartao("cliques", clicados, "Link clicado (e-mail)"),
        ],
    }


@router.get("/emails/postgres")
async def lista_emails_postgres(
    pool: PoolOrquestracao,
    page: Annotated[int, Query(ge=1)] = 1,
    status: str | None = None,
    cnpj_basico: str | None = None,
) -> dict[str, Any]:
    p = obter_identificadores_postgres()
    te = p.qual("emails_enviados")
    page = _page_clamped(page)
    offset = (page - 1) * PAGE_SIZE

    filtros: list[str] = []
    params: list[Any] = []
    status_f = _texto(status)
    cnpj_f = _busca_cnpj(cnpj_basico)
    if status_f:
        filtros.append(f"status_ultimo = {_append_param(params, status_f)}")
    if cnpj_f:
        filtros.append(f"COALESCE(contexto->>'cnpj_basico', '') ILIKE {_append_param(params, cnpj_f)}")
    where_sql = f"WHERE {' AND '.join(filtros)}" if filtros else ""

    total = int(await pool.fetchval(f"SELECT COUNT(*) FROM {te} {where_sql}", *params) or 0)
    rows = await pool.fetch(
        f"""
        SELECT
            *,
            COALESCE(contexto->>'cnpj_basico', NULL) AS cnpj_basico_dashboard
        FROM {te}
        {where_sql}
        ORDER BY criado_em DESC NULLS LAST, id DESC
        LIMIT {PAGE_SIZE} OFFSET {offset}
        """,
        *params,
    )
    itens = [_normalizar_linha_postgres_mensagem(registo_para_json(r), canal="email") for r in rows]
    return {"origem": "postgres", "tabela_logica": "emails_enviados", "itens": itens, **_meta(total, page)}


@router.get("/emails/redis-pendentes")
async def lista_emails_redis_pendentes(
    redis: RedisOrquestracao,
    page: Annotated[int, Query(ge=1)] = 1,
    cnpj_basico: str | None = None,
) -> dict[str, Any]:
    page = _page_clamped(page)
    busca = _texto(cnpj_basico)
    ids_raw = await redis.zrevrange(IDX_EMAIL_PEND, 0, -1)
    itens: list[dict[str, Any]] = []
    for ext in ids_raw:
        ext_s = ext.decode() if isinstance(ext, bytes) else str(ext)
        raw = await redis.hgetall(chave_email_pend(ext_s))
        if not raw:
            await redis.zrem(IDX_EMAIL_PEND, ext_s)
            continue
        ctx = decodificar_contexto_json_bruto(_h(raw, "contexto_json"))
        linha: dict[str, Any] = {
            "id_externo": _h(raw, "id_externo") or _h(raw, "external_id") or ext_s,
            "destinatario": _h(raw, "destinatario"),
            "tipo_template": _h(raw, "tipo_template"),
            "contexto": ctx if isinstance(ctx, dict) else {},
            "remetente": _h(raw, "remetente") or None,
            "fornecedor_id": _h(raw, "fornecedor_id") or _h(raw, "usuario_id") or None,
            "cnpj_basico": _h(raw, "cnpj_basico") or None,
            "origem": _h(raw, "origem"),
            "consulta_id": _h(raw, "consulta_id") or None,
            "criado_em": _h(raw, "criado_em"),
        }
        if busca and busca not in str(linha.get("cnpj_basico") or ""):
            continue
        itens.append(enriquecer_redis_email_pendente(linha))
    itens_pagina, total = _pagina_itens(itens, page)
    return {"origem": "redis", "tabela_logica": "emails_pendentes", "itens": itens_pagina, **_meta(total, page)}


@router.get("/emails/redis-esperando-confirmacao")
async def lista_emails_redis_esperando(
    redis: RedisOrquestracao,
    page: Annotated[int, Query(ge=1)] = 1,
    status: str | None = None,
    cnpj_basico: str | None = None,
) -> dict[str, Any]:
    page = _page_clamped(page)
    status_f = _texto(status)
    busca = _texto(cnpj_basico)
    ids_raw = await redis.zrevrange(IDX_EMAIL_CONF, 0, -1)
    itens: list[dict[str, Any]] = []
    for mid in ids_raw:
        mid_s = mid.decode() if isinstance(mid, bytes) else str(mid)
        raw = await redis.hgetall(chave_email_conf(mid_s))
        if not raw:
            await redis.zrem(IDX_EMAIL_CONF, mid_s)
            continue
        ctx = decodificar_contexto_json_bruto(_h(raw, "contexto_json"))
        linha = {
            "message_id_zenvia": mid_s,
            "id_externo": _h(raw, "id_externo") or _h(raw, "external_id"),
            "email_destinatario": _h(raw, "email_destinatario"),
            "tipo_template": _h(raw, "tipo_template"),
            "contexto": ctx if isinstance(ctx, dict) else {},
            "remetente": _h(raw, "remetente") or None,
            "fornecedor_id": _h(raw, "fornecedor_id") or _h(raw, "usuario_id") or None,
            "cnpj_basico": _h(raw, "cnpj_basico") or None,
            "consulta_id": _h(raw, "consulta_id") or None,
            "status_atual": _h(raw, "status_atual"),
            "criado_em": _h(raw, "criado_em"),
            "atualizado_em": _h(raw, "atualizado_em"),
            "ultimo_cause": _h(raw, "ultimo_cause"),
        }
        if status_f and status_f.upper() != str(linha.get("status_atual") or "").upper():
            continue
        if busca and busca not in str(linha.get("cnpj_basico") or ""):
            continue
        itens.append(enriquecer_redis_email_esperando(linha))
    itens_pagina, total = _pagina_itens(itens, page)
    return {
        "origem": "redis",
        "tabela_logica": "emails_esperando_confirmacao",
        "itens": itens_pagina,
        **_meta(total, page),
    }


@router.get("/sms/metricas")
async def metricas_sms(
    pool: PoolOrquestracao,
    redis: RedisOrquestracao,
) -> dict[str, Any]:
    p = obter_identificadores_postgres()
    ts = p.qual("sms_enviados")
    total = int(await pool.fetchval(f"SELECT COUNT(*) FROM {ts}") or 0)
    falhas = int(
        await pool.fetchval(
            f"SELECT COUNT(*) FROM {ts} WHERE status_ultimo = 'falha_definitiva'",
        )
        or 0,
    )
    entregues = int(
        await pool.fetchval(
            f"SELECT COUNT(*) FROM {ts} WHERE status_ultimo IN ('enviado', 'lido', 'clicado')",
        )
        or 0,
    )
    clicados = int(
        await pool.fetchval(
            f"SELECT COUNT(*) FROM {ts} WHERE status_ultimo = 'clicado'",
        )
        or 0,
    )
    pendentes = int(await redis.zcard(IDX_SMS_PEND) or 0)
    esperando = int(await redis.zcard(IDX_SMS_CONF) or 0)
    return {
        "sms_enviados_total": total,
        "sms_pendentes_fila": pendentes,
        "sms_esperando_confirmacao": esperando,
        "sms_falha_definitiva": falhas,
        "sms_entregues": entregues,
        "sms_clicados": clicados,
        "cartoes": [
            _cartao("enviados", total, "SMS registados"),
            _cartao("pendentes", pendentes, "Na fila a enviar"),
            _cartao("esperando_feedback", esperando, "Esperando confirmação"),
            _cartao("recusados", falhas, "Falha definitiva"),
            _cartao("entregues", entregues, "SMS entregues"),
            _cartao("cliques", clicados, "Link clicado (SMS)"),
        ],
    }


@router.get("/sms/postgres")
async def lista_sms_postgres(
    pool: PoolOrquestracao,
    page: Annotated[int, Query(ge=1)] = 1,
    status: str | None = None,
    cnpj_basico: str | None = None,
) -> dict[str, Any]:
    p = obter_identificadores_postgres()
    ts = p.qual("sms_enviados")
    page = _page_clamped(page)
    offset = (page - 1) * PAGE_SIZE

    filtros: list[str] = []
    params: list[Any] = []
    status_f = _texto(status)
    cnpj_f = _busca_cnpj(cnpj_basico)
    if status_f:
        filtros.append(f"status_ultimo = {_append_param(params, status_f)}")
    if cnpj_f:
        filtros.append(f"COALESCE(contexto->>'cnpj_basico', '') ILIKE {_append_param(params, cnpj_f)}")
    where_sql = f"WHERE {' AND '.join(filtros)}" if filtros else ""

    total = int(await pool.fetchval(f"SELECT COUNT(*) FROM {ts} {where_sql}", *params) or 0)
    rows = await pool.fetch(
        f"""
        SELECT
            *,
            COALESCE(contexto->>'cnpj_basico', NULL) AS cnpj_basico_dashboard
        FROM {ts}
        {where_sql}
        ORDER BY criado_em DESC NULLS LAST, id DESC
        LIMIT {PAGE_SIZE} OFFSET {offset}
        """,
        *params,
    )
    itens = [_normalizar_linha_postgres_mensagem(registo_para_json(r), canal="sms") for r in rows]
    return {"origem": "postgres", "tabela_logica": "sms_enviados", "itens": itens, **_meta(total, page)}


@router.get("/sms/redis-pendentes")
async def lista_sms_redis_pendentes(
    redis: RedisOrquestracao,
    page: Annotated[int, Query(ge=1)] = 1,
    cnpj_basico: str | None = None,
) -> dict[str, Any]:
    page = _page_clamped(page)
    busca = _texto(cnpj_basico)
    ids_raw = await redis.zrevrange(IDX_SMS_PEND, 0, -1)
    itens: list[dict[str, Any]] = []
    for ext in ids_raw:
        ext_s = ext.decode() if isinstance(ext, bytes) else str(ext)
        raw = await redis.hgetall(chave_sms_pend(ext_s))
        if not raw:
            await redis.zrem(IDX_SMS_PEND, ext_s)
            continue
        ctx = decodificar_contexto_json_bruto(_h(raw, "contexto_json"))
        linha = {
            "id_externo": _h(raw, "id_externo") or _h(raw, "external_id") or ext_s,
            "telefone": _h(raw, "telefone"),
            "tipo_template": _h(raw, "tipo_template"),
            "contexto": ctx if isinstance(ctx, dict) else {},
            "remetente": _h(raw, "remetente") or None,
            "origem": _h(raw, "origem"),
            "fornecedor_id": _h(raw, "fornecedor_id") or _h(raw, "usuario_id") or None,
            "cnpj_basico": _h(raw, "cnpj_basico") or None,
            "consulta_id": _h(raw, "consulta_id") or None,
            "criado_em": _h(raw, "criado_em"),
        }
        if busca and busca not in str(linha.get("cnpj_basico") or ""):
            continue
        itens.append(enriquecer_redis_sms_pendente(linha))
    itens_pagina, total = _pagina_itens(itens, page)
    return {"origem": "redis", "tabela_logica": "sms_pendentes", "itens": itens_pagina, **_meta(total, page)}


@router.get("/sms/redis-esperando-confirmacao")
async def lista_sms_redis_esperando(
    redis: RedisOrquestracao,
    page: Annotated[int, Query(ge=1)] = 1,
    status: str | None = None,
    cnpj_basico: str | None = None,
) -> dict[str, Any]:
    page = _page_clamped(page)
    status_f = _texto(status)
    busca = _texto(cnpj_basico)
    ids_raw = await redis.zrevrange(IDX_SMS_CONF, 0, -1)
    itens: list[dict[str, Any]] = []
    for mid in ids_raw:
        mid_s = mid.decode() if isinstance(mid, bytes) else str(mid)
        raw = await redis.hgetall(chave_sms_conf(mid_s))
        if not raw:
            await redis.zrem(IDX_SMS_CONF, mid_s)
            continue
        ctx = decodificar_contexto_json_bruto(_h(raw, "contexto_json"))
        linha = {
            "message_id_zenvia": mid_s,
            "id_externo": _h(raw, "id_externo") or _h(raw, "external_id"),
            "telefone_destinatario": _h(raw, "telefone_destinatario"),
            "tipo_template": _h(raw, "tipo_template"),
            "contexto": ctx if isinstance(ctx, dict) else {},
            "remetente": _h(raw, "remetente") or None,
            "fornecedor_id": _h(raw, "fornecedor_id") or _h(raw, "usuario_id") or None,
            "cnpj_basico": _h(raw, "cnpj_basico") or None,
            "consulta_id": _h(raw, "consulta_id") or None,
            "status_atual": _h(raw, "status_atual"),
            "criado_em": _h(raw, "criado_em"),
            "atualizado_em": _h(raw, "atualizado_em"),
        }
        if status_f and status_f.upper() != str(linha.get("status_atual") or "").upper():
            continue
        if busca and busca not in str(linha.get("cnpj_basico") or ""):
            continue
        itens.append(enriquecer_redis_sms_esperando(linha))
    itens_pagina, total = _pagina_itens(itens, page)
    return {
        "origem": "redis",
        "tabela_logica": "sms_esperando_confirmacao",
        "itens": itens_pagina,
        **_meta(total, page),
    }


@router.get("/engajamento/metricas")
async def metricas_engajamento(pool: PoolOrquestracao) -> dict[str, Any]:
    resumo = await _resumo_engajamento(pool)
    total = resumo["total_monitorados"]
    sem_email = max(total - resumo["usuarios_com_email"], 0)
    sem_telefone = max(total - resumo["usuarios_com_telefone"], 0)
    sem_contato = max(total - resumo["usuarios_com_algum_contato"], 0)
    nao_convertidos = max(total - resumo["usuarios_convertidos"], 0)
    canais = await _conversoes_por_canal(pool)

    return {
        "cartoes": [
            _cartao(
                "monitorados",
                total,
                "Usuários monitorados",
                total=total,
                segmentos=[
                    _segmento("Com contato", resumo["usuarios_com_algum_contato"], "success"),
                    _segmento("Sem contato", sem_contato, "neutral"),
                ],
            ),
            _cartao(
                "usuarios_email",
                resumo["usuarios_com_email"],
                "Usuários com e-mail",
                total=total,
                segmentos=[
                    _segmento("Com e-mail", resumo["usuarios_com_email"], "info"),
                    _segmento("Sem e-mail", sem_email, "neutral"),
                ],
            ),
            _cartao(
                "usuarios_telefone",
                resumo["usuarios_com_telefone"],
                "Usuários com telefone",
                total=total,
                segmentos=[
                    _segmento("Com telefone", resumo["usuarios_com_telefone"], "warning"),
                    _segmento("Sem telefone", sem_telefone, "neutral"),
                ],
            ),
            _cartao(
                "usuarios_convertidos",
                resumo["usuarios_convertidos"],
                "Usuários convertidos",
                total=total,
                segmentos=[
                    _segmento("Convertidos", resumo["usuarios_convertidos"], "success"),
                    _segmento("Não convertidos", nao_convertidos, "neutral"),
                ],
            ),
        ],
        "conversoes_canal": [
            _segmento("Só e-mail", canais["so_email"], "info"),
            _segmento("Só SMS", canais["so_sms"], "warning"),
            _segmento("Ambos", canais["ambos"], "success"),
            _segmento("Sem histórico", canais["sem_historico"], "neutral"),
        ],
        "resumo": resumo,
    }


@router.get("/engajamento/fornecedores")
async def lista_engajamento_fornecedores(
    pool: PoolOrquestracao,
    page: Annotated[int, Query(ge=1)] = 1,
    status: str | None = None,
    cnpj_basico: str | None = None,
) -> dict[str, Any]:
    p = obter_identificadores_postgres()
    te = p.qual("engajamento_fornecedores")
    tf = p.qual("fornecedores")
    page = _page_clamped(page)
    offset = (page - 1) * PAGE_SIZE

    filtros: list[str] = []
    params: list[Any] = []
    status_f = _texto(status)
    cnpj_f = _busca_cnpj(cnpj_basico)
    if cnpj_f:
        filtros.append(f"e.cnpj_basico ILIKE {_append_param(params, cnpj_f)}")
    if status_f:
        marcador = _append_param(params, status_f)
        filtros.append(f"(e.engajamento_email = {marcador} OR e.engajamento_sms = {marcador})")
    where_sql = f"WHERE {' AND '.join(filtros)}" if filtros else ""

    total = int(await pool.fetchval(f"SELECT COUNT(*) FROM {te} AS e {where_sql}", *params) or 0)
    rows = await pool.fetch(
        f"""
        SELECT
            e.*,
            COALESCE(NULLIF(f.nome, ''), NULLIF(e.nome_fantasia, ''), e.cnpj_basico) AS nome_fornecedor
        FROM {te} AS e
        LEFT JOIN {tf} AS f ON f.cnpj_basico = e.cnpj_basico
        {where_sql}
        ORDER BY e.engajamento_atualizado_em DESC NULLS LAST, e.cnpj_basico DESC
        LIMIT {PAGE_SIZE} OFFSET {offset}
        """,
        *params,
    )
    itens = [registo_para_json(r) for r in rows]
    return {
        "origem": "postgres",
        "tabela_logica": "engajamento_fornecedores",
        "itens": itens,
        **_meta(total, page),
    }

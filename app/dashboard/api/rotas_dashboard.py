from __future__ import annotations
import math
from datetime import date, datetime, timedelta
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
from app.reenvio.servicos.n8n_claims import claim_n8n_ativo

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


def _validar_periodo_metricas(
    periodo_inicio: datetime | None,
    periodo_fim: datetime | None,
) -> tuple[datetime, datetime] | None:
    if periodo_inicio is None and periodo_fim is None:
        return None
    if periodo_inicio is None or periodo_fim is None:
        raise HTTPException(
            status_code=400,
            detail="Informe periodo_inicio e periodo_fim juntos, ou omita ambos.",
        )
    if periodo_inicio > periodo_fim:
        raise HTTPException(
            status_code=400,
            detail="periodo_inicio não pode ser maior que periodo_fim",
        )
    return periodo_inicio, periodo_fim


def _where_com_periodo(
    params: list[Any],
    periodo: tuple[datetime, datetime] | None,
    condicao: str = "",
) -> str:
    partes: list[str] = []
    if condicao:
        partes.append(condicao)
    if periodo:
        p_ini = _append_param(params, periodo[0])
        p_fim = _append_param(params, periodo[1])
        partes.append(f"criado_em >= {p_ini} AND criado_em <= {p_fim}")
    if not partes:
        return ""
    return " WHERE " + " AND ".join(partes)


async def _pg_count_periodo(
    pool: PoolOrquestracao,
    tabela: str,
    periodo: tuple[datetime, datetime] | None,
    condicao: str = "",
) -> int:
    params: list[Any] = []
    where = _where_com_periodo(params, periodo, condicao)
    return int(await pool.fetchval(f"SELECT COUNT(*) FROM {tabela}{where}", *params) or 0)


async def _redis_count_pendentes(
    redis: RedisOrquestracao,
    idx_key: str,
    periodo: tuple[datetime, datetime] | None,
) -> int:
    if not periodo:
        return int(await redis.zcard(idx_key) or 0)
    return int(
        await redis.zcount(
            idx_key,
            periodo[0].timestamp(),
            periodo[1].timestamp(),
        )
        or 0,
    )


def _epoch_criado_em_hash(raw: dict[Any, Any]) -> float | None:
    criado = _h(raw, "criado_em")
    if not criado:
        return None
    try:
        return float(criado)
    except ValueError:
        return None


async def _redis_count_esperando(
    redis: RedisOrquestracao,
    idx_key: str,
    chave_hash_fn,
    periodo: tuple[datetime, datetime] | None,
) -> int:
    if not periodo:
        return int(await redis.zcard(idx_key) or 0)
    min_ts = periodo[0].timestamp()
    max_ts = periodo[1].timestamp()
    ids_raw = await redis.zrange(idx_key, 0, -1)
    total = 0
    for mid in ids_raw:
        mid_s = mid.decode() if isinstance(mid, bytes) else str(mid)
        raw = await redis.hgetall(chave_hash_fn(mid_s))
        if not raw:
            continue
        ts = _epoch_criado_em_hash(raw)
        if ts is not None and min_ts <= ts <= max_ts:
            total += 1
    return total


def _meta_periodo_metricas(periodo: tuple[datetime, datetime] | None) -> dict[str, Any]:
    if not periodo:
        return {"periodo": None}
    return {
        "periodo": {
            "inicio": periodo[0].isoformat(),
            "fim": periodo[1].isoformat(),
        },
    }


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


_STATUS_ENTREGUES_SQL = "status_ultimo IN ('enviado', 'lido', 'clicado', 'lido_maquina')"
_STATUS_ABERTOS_SQL = "status_ultimo IN ('lido', 'clicado', 'lido_maquina')"


def _segmento_barra(
    chave: str,
    rotulo: str,
    valor: int,
    cor: str,
    *,
    aba: str = "postgres",
    status: str | None = None,
    status_grupo: str | None = None,
) -> dict[str, Any]:
    filtro: dict[str, str] = {"aba": aba}
    if status:
        filtro["status"] = status
    if status_grupo:
        filtro["status_grupo"] = status_grupo
    return {
        "chave": chave,
        "rotulo": rotulo,
        "valor": int(valor),
        "cor": cor,
        "filtro": filtro,
    }


def _barra_status_email(
    total: int,
    entregues: int,
    abertos: int,
    clicados: int,
    erros: int,
) -> dict[str, Any]:
    return {
        "total_rotulo": "enviados",
        "total": int(total),
        "segmentos": [
            _segmento_barra("entregues", "recebidos", entregues, "light", status_grupo="entregues"),
            _segmento_barra("abertos", "abertos", abertos, "medium", status_grupo="abertos"),
            _segmento_barra("clicados", "clicados", clicados, "navy", status="clicado"),
            _segmento_barra("erros", "erros", erros, "error", status="falha_definitiva"),
        ],
    }


def _barra_status_sms(
    total: int,
    entregues: int,
    abertos: int,
    clicados: int,
    erros: int,
) -> dict[str, Any]:
    return {
        "total_rotulo": "enviados",
        "total": int(total),
        "segmentos": [
            _segmento_barra("entregues", "recebidos", entregues, "light", status_grupo="entregues"),
            _segmento_barra("abertos", "abertos", abertos, "medium", status_grupo="abertos"),
            _segmento_barra("clicados", "clicados", clicados, "navy", status="clicado"),
            _segmento_barra("erros", "erros", erros, "error", status="falha_definitiva"),
        ],
    }


def _where_status_grupo(canal: str, status_grupo: str) -> str | None:
    g = (status_grupo or "").strip().lower()
    if g == "entregues":
        return _STATUS_ENTREGUES_SQL
    if g == "abertos":
        return _STATUS_ABERTOS_SQL if canal == "email" else "status_ultimo IN ('lido', 'clicado')"
    return None


def _cartao(
    chave: str,
    valor: int,
    legenda: str,
    *,
    total: int | None = None,
    segmentos: list[dict[str, Any]] | None = None,
    detalhe: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {"chave": chave, "valor": int(valor), "legenda": legenda}
    if total is not None:
        out["total"] = int(total)
    if segmentos:
        out["segmentos"] = segmentos
    if detalhe:
        out["detalhe"] = detalhe
    return out


def _detalhe_lidos_maquina(qtd: int) -> str | None:
    if qtd <= 0:
        return None
    return f"({qtd} abertos por máquina)"


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
            ) AS usuarios_convertidos,
            COUNT(*) FILTER (
                WHERE jsonb_array_length(COALESCE(contatos_email, '[]'::jsonb)) = 0
            ) AS email_sem_lista,
            COUNT(*) FILTER (
                WHERE jsonb_array_length(COALESCE(contatos_email, '[]'::jsonb)) > 0
                  AND lower(trim(COALESCE(e.engajamento_email::text, ''))) = 'ativo'
            ) AS email_agg_ativo,
            COUNT(*) FILTER (
                WHERE jsonb_array_length(COALESCE(contatos_email, '[]'::jsonb)) > 0
                  AND lower(trim(COALESCE(e.engajamento_email::text, ''))) = 'em_analise'
            ) AS email_agg_em_analise,
            COUNT(*) FILTER (
                WHERE jsonb_array_length(COALESCE(contatos_email, '[]'::jsonb)) > 0
                  AND lower(trim(COALESCE(e.engajamento_email::text, ''))) = 'inativo'
            ) AS email_agg_inativo,
            COUNT(*) FILTER (
                WHERE jsonb_array_length(COALESCE(contatos_email, '[]'::jsonb)) > 0
                  AND lower(trim(COALESCE(e.engajamento_email::text, ''))) NOT IN (
                      'ativo', 'em_analise', 'inativo'
                  )
            ) AS email_agg_outros,
            COUNT(*) FILTER (
                WHERE jsonb_array_length(COALESCE(contatos_sms, '[]'::jsonb)) = 0
            ) AS sms_sem_lista,
            COUNT(*) FILTER (
                WHERE jsonb_array_length(COALESCE(contatos_sms, '[]'::jsonb)) > 0
                  AND lower(trim(COALESCE(e.engajamento_sms::text, ''))) = 'ativo'
            ) AS sms_agg_ativo,
            COUNT(*) FILTER (
                WHERE jsonb_array_length(COALESCE(contatos_sms, '[]'::jsonb)) > 0
                  AND lower(trim(COALESCE(e.engajamento_sms::text, ''))) = 'em_analise'
            ) AS sms_agg_em_analise,
            COUNT(*) FILTER (
                WHERE jsonb_array_length(COALESCE(contatos_sms, '[]'::jsonb)) > 0
                  AND lower(trim(COALESCE(e.engajamento_sms::text, ''))) = 'inativo'
            ) AS sms_agg_inativo,
            COUNT(*) FILTER (
                WHERE jsonb_array_length(COALESCE(contatos_sms, '[]'::jsonb)) > 0
                  AND lower(trim(COALESCE(e.engajamento_sms::text, ''))) NOT IN (
                      'ativo', 'em_analise', 'inativo'
                  )
            ) AS sms_agg_outros
        FROM {te} AS e
        """,
    )
    email_outros = int(row["email_agg_outros"] or 0)
    sms_outros = int(row["sms_agg_outros"] or 0)
    return {
        "total_monitorados": int(row["total_monitorados"] or 0),
        "usuarios_com_email": int(row["usuarios_com_email"] or 0),
        "usuarios_com_telefone": int(row["usuarios_com_telefone"] or 0),
        "usuarios_com_algum_contato": int(row["usuarios_com_algum_contato"] or 0),
        "usuarios_convertidos": int(row["usuarios_convertidos"] or 0),
        "email_sem_lista": int(row["email_sem_lista"] or 0),
        "email_agg_ativo": int(row["email_agg_ativo"] or 0),
        "email_agg_em_analise": int(row["email_agg_em_analise"] or 0) + email_outros,
        "email_agg_inativo": int(row["email_agg_inativo"] or 0),
        "sms_sem_lista": int(row["sms_sem_lista"] or 0),
        "sms_agg_ativo": int(row["sms_agg_ativo"] or 0),
        "sms_agg_em_analise": int(row["sms_agg_em_analise"] or 0) + sms_outros,
        "sms_agg_inativo": int(row["sms_agg_inativo"] or 0),
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
                    WHERE COALESCE(NULLIF(trim(coalesce(em.cnpj_basico, '')), ''), em.contexto->>'cnpj_basico', '') = e.cnpj_basico
                ) AS tem_email,
                EXISTS (
                    SELECT 1
                    FROM {tsm} AS sm
                    WHERE COALESCE(NULLIF(trim(coalesce(sm.cnpj_basico, '')), ''), sm.contexto->>'cnpj_basico', '') = e.cnpj_basico
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


def _expr_cnpj_mensagem(alias: str) -> str:
    return f"""COALESCE(
        NULLIF(trim(coalesce({alias}.cnpj_basico, '')), ''),
        {alias}.contexto->>'cnpj_basico',
        ''
    )"""


def _etapa_funil(chave: str, rotulo: str, valor: int, escopo: str) -> dict[str, Any]:
    return {
        "chave": chave,
        "rotulo": rotulo,
        "valor": int(valor),
        "escopo": escopo,
    }


def _funil_canal(canal: str, titulo: str, etapas: list[dict[str, Any]]) -> dict[str, Any]:
    return {"canal": canal, "titulo": titulo, "etapas": etapas}


async def _count_cnpj_distintos_periodo(
    pool: PoolOrquestracao,
    *,
    tabela: str,
    alias: str,
    inicio: date,
    fim: date,
    condicao_extra: str = "",
) -> int:
    cnpj = _expr_cnpj_mensagem(alias)
    extra = f" AND ({condicao_extra})" if condicao_extra else ""
    return int(
        await pool.fetchval(
            f"""
            SELECT COUNT(DISTINCT {cnpj})
            FROM {tabela} AS {alias}
            WHERE {alias}.criado_em::date BETWEEN $1 AND $2
              AND {cnpj} <> ''
            {extra}
            """,
            inicio,
            fim,
        )
        or 0
    )


async def _funis_home(
    pool: PoolOrquestracao,
    *,
    inicio: date,
    fim: date,
    resumo_eng: dict[str, int],
    canais: dict[str, int],
) -> dict[str, Any]:
    p = obter_identificadores_postgres()
    te = p.qual("emails_enviados")
    ts = p.qual("sms_enviados")

    monitorados = int(resumo_eng["total_monitorados"] or 0)
    com_email = int(resumo_eng["usuarios_com_email"] or 0)
    com_telefone = int(resumo_eng["usuarios_com_telefone"] or 0)

    email_receberam = await _count_cnpj_distintos_periodo(
        pool, tabela=te, alias="m", inicio=inicio, fim=fim
    )
    email_lidos = await _count_cnpj_distintos_periodo(
        pool,
        tabela=te,
        alias="m",
        inicio=inicio,
        fim=fim,
        condicao_extra="m.status_ultimo IN ('lido', 'clicado')",
    )
    email_clicados = await _count_cnpj_distintos_periodo(
        pool,
        tabela=te,
        alias="m",
        inicio=inicio,
        fim=fim,
        condicao_extra="m.status_ultimo = 'clicado'",
    )
    convertidos_email = int(canais.get("so_email") or 0) + int(canais.get("ambos") or 0)

    sms_receberam = await _count_cnpj_distintos_periodo(
        pool, tabela=ts, alias="m", inicio=inicio, fim=fim
    )
    sms_entregues = await _count_cnpj_distintos_periodo(
        pool,
        tabela=ts,
        alias="m",
        inicio=inicio,
        fim=fim,
        condicao_extra="m.status_ultimo IN ('enviado', 'lido', 'clicado')",
    )
    sms_clicados = await _count_cnpj_distintos_periodo(
        pool,
        tabela=ts,
        alias="m",
        inicio=inicio,
        fim=fim,
        condicao_extra="m.status_ultimo = 'clicado'",
    )
    convertidos_sms = int(canais.get("so_sms") or 0) + int(canais.get("ambos") or 0)

    return {
        "email": _funil_canal(
            "email",
            "Funil de e-mail",
            [
                _etapa_funil("monitorados", "Usuários monitorados", monitorados, "estoque"),
                _etapa_funil("com_contato", "Com e-mail cadastrado", com_email, "estoque"),
                _etapa_funil(
                    "receberam",
                    "Receberam e-mail no período",
                    email_receberam,
                    "periodo",
                ),
                _etapa_funil("lidos", "Abriram o e-mail", email_lidos, "periodo"),
                _etapa_funil("clicados", "Clicaram no link", email_clicados, "periodo"),
                _etapa_funil(
                    "convertidos",
                    "Convertidos (histórico e-mail)",
                    convertidos_email,
                    "periodo",
                ),
            ],
        ),
        "sms": _funil_canal(
            "sms",
            "Funil de SMS",
            [
                _etapa_funil("monitorados", "Usuários monitorados", monitorados, "estoque"),
                _etapa_funil("com_contato", "Com telefone cadastrado", com_telefone, "estoque"),
                _etapa_funil(
                    "receberam",
                    "Receberam SMS no período",
                    sms_receberam,
                    "periodo",
                ),
                _etapa_funil("entregues", "SMS entregues", sms_entregues, "periodo"),
                _etapa_funil("clicados", "Clicaram no link", sms_clicados, "periodo"),
                _etapa_funil(
                    "convertidos",
                    "Convertidos (histórico SMS)",
                    convertidos_sms,
                    "periodo",
                ),
            ],
        ),
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
    emails_lidos_maquina = int(
        await pool.fetchval(
            f"""
            SELECT COUNT(*)
            FROM {te}
            WHERE criado_em::date BETWEEN $1 AND $2
              AND status_ultimo = 'lido_maquina'
            """,
            inicio,
            fim,
        )
        or 0
    )
    emails_aberturas_total = emails_lidos + emails_lidos_maquina

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

    emails_nao_lidos = max(total_emails - emails_aberturas_total, 0)
    sms_pendentes = max(total_sms - sms_entregues, 0)
    canais = await _conversoes_por_canal(pool, inicio=inicio, fim=fim)
    total_canais = sum(canais.values())
    funis = await _funis_home(
        pool,
        inicio=inicio,
        fim=fim,
        resumo_eng=resumo_eng,
        canais=canais,
    )

    return {
        "periodo": {
            "data_inicio": inicio.isoformat(),
            "data_fim": fim.isoformat(),
            "total_dias": len(_datas_periodo(inicio, fim)),
        },
        "emails_lidos_maquina": emails_lidos_maquina,
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
                "valor": emails_aberturas_total,
                "total": total_emails,
                "detalhe": _detalhe_lidos_maquina(emails_lidos_maquina),
                "segmentos": [
                    _segmento("Lidos", emails_aberturas_total, "success"),
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
        "funis": funis,
    }


@router.get("/emails/metricas")
async def metricas_emails(
    pool: PoolOrquestracao,
    redis: RedisOrquestracao,
    periodo_inicio: datetime | None = None,
    periodo_fim: datetime | None = None,
) -> dict[str, Any]:
    periodo = _validar_periodo_metricas(periodo_inicio, periodo_fim)
    p = obter_identificadores_postgres()
    te = p.qual("emails_enviados")
    total = await _pg_count_periodo(pool, te, periodo)
    falhas = await _pg_count_periodo(pool, te, periodo, "status_ultimo = 'falha_definitiva'")
    lidos = await _pg_count_periodo(
        pool,
        te,
        periodo,
        "status_ultimo IN ('lido', 'clicado')",
    )
    lidos_maquina = await _pg_count_periodo(
        pool,
        te,
        periodo,
        "status_ultimo = 'lido_maquina'",
    )
    aberturas_total = lidos + lidos_maquina
    clicados = await _pg_count_periodo(pool, te, periodo, "status_ultimo = 'clicado'")
    entregues = await _pg_count_periodo(pool, te, periodo, _STATUS_ENTREGUES_SQL)
    pendentes = await _redis_count_pendentes(redis, IDX_EMAIL_PEND, periodo)
    esperando = await _redis_count_esperando(redis, IDX_EMAIL_CONF, chave_email_conf, periodo)
    return {
        **_meta_periodo_metricas(periodo),
        "emails_enviados_total": total,
        "emails_entregues": entregues,
        "emails_pendentes_pre_envio": pendentes,
        "emails_esperando_confirmacao": esperando,
        "emails_falha_definitiva": falhas,
        "emails_lidos": lidos,
        "emails_lidos_maquina": lidos_maquina,
        "emails_clicados": clicados,
        "barra_status": _barra_status_email(total, entregues, aberturas_total, clicados, falhas),
        "cartoes": [
            _cartao("enviados", total, "E-mails registados"),
            _cartao("pendentes", pendentes, "Na fila pré-envio"),
            _cartao("recusados", falhas, "Falha definitiva"),
            _cartao("esperando_feedback", esperando, "Esperando confirmação"),
            _cartao(
                "abertos",
                aberturas_total,
                "Lidos",
                detalhe=_detalhe_lidos_maquina(lidos_maquina),
            ),
            _cartao("cliques", clicados, "Link clicado (e-mail)"),
        ],
    }


@router.get("/emails/postgres")
async def lista_emails_postgres(
    pool: PoolOrquestracao,
    page: Annotated[int, Query(ge=1)] = 1,
    status: str | None = None,
    status_grupo: str | None = None,
    cnpj_basico: str | None = None,
) -> dict[str, Any]:
    p = obter_identificadores_postgres()
    te = p.qual("emails_enviados")
    page = _page_clamped(page)
    offset = (page - 1) * PAGE_SIZE

    filtros: list[str] = []
    params: list[Any] = []
    status_f = _texto(status)
    grupo_sql = _where_status_grupo("email", status_grupo or "")
    cnpj_f = _busca_cnpj(cnpj_basico)
    if status_f:
        filtros.append(f"status_ultimo = {_append_param(params, status_f)}")
    elif grupo_sql:
        filtros.append(grupo_sql)
    if cnpj_f:
        filtros.append(
            f"COALESCE(NULLIF(trim(coalesce(cnpj_basico, '')), ''), contexto->>'cnpj_basico', '') ILIKE {_append_param(params, cnpj_f)}"
        )
    where_sql = f"WHERE {' AND '.join(filtros)}" if filtros else ""

    total = int(await pool.fetchval(f"SELECT COUNT(*) FROM {te} {where_sql}", *params) or 0)
    rows = await pool.fetch(
        f"""
        SELECT
            *,
            COALESCE(
                NULLIF(trim(coalesce(cnpj_basico, '')), ''),
                contexto->>'cnpj_basico',
                NULL
            ) AS cnpj_basico_dashboard
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
            "claim_n8n_ativo": await claim_n8n_ativo(redis, canal="email", id_externo=ext_s),
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
    periodo_inicio: datetime | None = None,
    periodo_fim: datetime | None = None,
) -> dict[str, Any]:
    periodo = _validar_periodo_metricas(periodo_inicio, periodo_fim)
    p = obter_identificadores_postgres()
    ts = p.qual("sms_enviados")
    total = await _pg_count_periodo(pool, ts, periodo)
    falhas = await _pg_count_periodo(pool, ts, periodo, "status_ultimo = 'falha_definitiva'")
    entregues = await _pg_count_periodo(
        pool,
        ts,
        periodo,
        "status_ultimo IN ('enviado', 'lido', 'clicado')",
    )
    clicados = await _pg_count_periodo(pool, ts, periodo, "status_ultimo = 'clicado'")
    entregues_barra = await _pg_count_periodo(pool, ts, periodo, _STATUS_ENTREGUES_SQL)
    abertos_sms = await _pg_count_periodo(pool, ts, periodo, "status_ultimo IN ('lido', 'clicado')")
    pendentes = await _redis_count_pendentes(redis, IDX_SMS_PEND, periodo)
    esperando = await _redis_count_esperando(redis, IDX_SMS_CONF, chave_sms_conf, periodo)
    return {
        **_meta_periodo_metricas(periodo),
        "sms_enviados_total": total,
        "sms_entregues": entregues_barra,
        "sms_pendentes_fila": pendentes,
        "sms_esperando_confirmacao": esperando,
        "sms_falha_definitiva": falhas,
        "sms_entregues_card": entregues,
        "sms_clicados": clicados,
        "barra_status": _barra_status_sms(total, entregues_barra, abertos_sms, clicados, falhas),
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
    status_grupo: str | None = None,
    cnpj_basico: str | None = None,
) -> dict[str, Any]:
    p = obter_identificadores_postgres()
    ts = p.qual("sms_enviados")
    page = _page_clamped(page)
    offset = (page - 1) * PAGE_SIZE

    filtros: list[str] = []
    params: list[Any] = []
    status_f = _texto(status)
    grupo_sql = _where_status_grupo("sms", status_grupo or "")
    cnpj_f = _busca_cnpj(cnpj_basico)
    if status_f:
        filtros.append(f"status_ultimo = {_append_param(params, status_f)}")
    elif grupo_sql:
        filtros.append(grupo_sql)
    if cnpj_f:
        filtros.append(
            f"COALESCE(NULLIF(trim(coalesce(cnpj_basico, '')), ''), contexto->>'cnpj_basico', '') ILIKE {_append_param(params, cnpj_f)}"
        )
    where_sql = f"WHERE {' AND '.join(filtros)}" if filtros else ""

    total = int(await pool.fetchval(f"SELECT COUNT(*) FROM {ts} {where_sql}", *params) or 0)
    rows = await pool.fetch(
        f"""
        SELECT
            *,
            COALESCE(
                NULLIF(trim(coalesce(cnpj_basico, '')), ''),
                contexto->>'cnpj_basico',
                NULL
            ) AS cnpj_basico_dashboard
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
            "claim_n8n_ativo": await claim_n8n_ativo(redis, canal="sms", id_externo=ext_s),
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
    sem_contato = max(total - resumo["usuarios_com_algum_contato"], 0)
    nao_convertidos = max(total - resumo["usuarios_convertidos"], 0)
    canais = await _conversoes_por_canal(pool)

    email_com_lista = (
        resumo["email_agg_ativo"]
        + resumo["email_agg_em_analise"]
        + resumo["email_agg_inativo"]
    )
    sms_com_lista = (
        resumo["sms_agg_ativo"] + resumo["sms_agg_em_analise"] + resumo["sms_agg_inativo"]
    )

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
                email_com_lista,
                "Engajamento e-mail",
                total=total,
                segmentos=[
                    _segmento("Ativo", resumo["email_agg_ativo"], "success"),
                    _segmento("Em análise", resumo["email_agg_em_analise"], "info"),
                    _segmento("Inativo", resumo["email_agg_inativo"], "danger"),
                    _segmento("Sem e-mail", resumo["email_sem_lista"], "neutral"),
                ],
            ),
            _cartao(
                "usuarios_telefone",
                sms_com_lista,
                "Engajamento SMS",
                total=total,
                segmentos=[
                    _segmento("Ativo", resumo["sms_agg_ativo"], "success"),
                    _segmento("Em análise", resumo["sms_agg_em_analise"], "info"),
                    _segmento("Inativo", resumo["sms_agg_inativo"], "danger"),
                    _segmento("Sem telefone", resumo["sms_sem_lista"], "neutral"),
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


def _filtro_apenas_convertidos(convertidos: str | None) -> bool:
    s = (convertidos or "").strip().lower()
    return s in ("1", "true", "sim", "yes", "on")


@router.get("/engajamento/fornecedores")
async def lista_engajamento_fornecedores(
    pool: PoolOrquestracao,
    page: Annotated[int, Query(ge=1)] = 1,
    status: str | None = None,
    cnpj_basico: str | None = None,
    convertidos: str | None = None,
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
    if _filtro_apenas_convertidos(convertidos):
        filtros.append("e.cadastrado_primeiro_contato = false")
        filtros.append(
            f"EXISTS (SELECT 1 FROM {tf} AS fx WHERE fx.cnpj_basico = e.cnpj_basico)",
        )
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

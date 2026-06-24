from __future__ import annotations
import asyncio
import logging
import math
import time
from datetime import date, datetime, timedelta
from typing import Annotated, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from app.config.postgres_identificadores import obter_identificadores_postgres
from app.dashboard.servicos.exibicao import (
    enriquecer_linha_postgres,
    enriquecer_linha_postgres_ligacao,
    enriquecer_redis_email_esperando,
    enriquecer_redis_email_pendente,
    enriquecer_redis_ligacao_pendente,
    enriquecer_redis_sms_esperando,
    enriquecer_redis_sms_pendente,
)
from app.dashboard.servicos.ordenar_engajamento_lista import (
    expr_aparicoes_30d,
    expr_aparicoes_total,
    filtros_sql_por_ordenar,
    normalizar_ordenar_engajamento,
    order_by_sql_engajamento,
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
from app.ligacoes.repositorios.redis_ligacoes_pendente import KEY_INDEX as IDX_LIG_PEND
from app.ligacoes.repositorios.redis_ligacoes_pendente import chave_hash as chave_lig_pend
from app.reenvio.repositorios.postgres_telefone_engajamento import (
    listar_contatos_sms_por_cnpjs,
    listar_telefones_agrupados_por_cnpjs,
)
from app.reenvio.repositorios.redis_sms_pendente import KEY_INDEX as IDX_SMS_PEND
from app.reenvio.repositorios.redis_sms_pendente import chave_hash as chave_sms_pend
from app.config.config import obter_configuracao
from app.reenvio.servicos.n8n_claims import claim_n8n_ativo

router = APIRouter(
    prefix="/v1/interno/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(usuario_logado)],
)

PAGE_SIZE = 10

_coluna_data_fornecedor_cache: str | None | bool = False
_tabela_aparicoes_cache: bool | None = None


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


def _timestamp_criado_em_valor(criado: str | None) -> float | None:
    if not criado:
        return None
    try:
        return float(criado)
    except ValueError:
        pass
    try:
        normalizado = criado.replace("Z", "+00:00")
        return datetime.fromisoformat(normalizado).timestamp()
    except ValueError:
        return None


def _epoch_criado_em_hash(raw: dict[Any, Any]) -> float | None:
    return _timestamp_criado_em_valor(_h(raw, "criado_em"))


def _linha_dentro_periodo(
    criado_em: Any,
    periodo: tuple[datetime, datetime] | None,
) -> bool:
    if not periodo:
        return True
    ts: float | None = None
    if isinstance(criado_em, (int, float)):
        ts = float(criado_em)
    elif criado_em is not None:
        ts = _timestamp_criado_em_valor(str(criado_em))
    if ts is None:
        return False
    return periodo[0].timestamp() <= ts <= periodo[1].timestamp()


def _append_filtro_periodo_sql(
    filtros: list[str],
    params: list[Any],
    periodo: tuple[datetime, datetime] | None,
) -> None:
    if not periodo:
        return
    p_ini = _append_param(params, periodo[0])
    p_fim = _append_param(params, periodo[1])
    filtros.append(f"criado_em >= {p_ini} AND criado_em <= {p_fim}")


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
_SMS_ENTREGUES_SQL = "status_ultimo IN ('enviado', 'lido', 'clicado')"
_SMS_RECEBIDOS_PAINEL_SQL = _SMS_ENTREGUES_SQL
_STATUS_FATURAVEL_SQL = "status_ultimo IS DISTINCT FROM 'falha_definitiva'"
_VALOR_UNITARIO_EMAIL_HOME = 0.004
_VALOR_UNITARIO_SMS_HOME = 0.1

_logger = logging.getLogger(__name__)


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


def _barra_status_ligacoes(
    total: int,
    concluidos: int,
    sem_resposta: int,
    falhas: int,
) -> dict[str, Any]:
    return {
        "total_rotulo": "enviadas",
        "total": int(total),
        "segmentos": [
            _segmento_barra("concluido", "concluídas", concluidos, "success", status="concluido"),
            _segmento_barra("sem_resposta", "sem resposta", sem_resposta, "warning", status="sem_resposta"),
            _segmento_barra("falha", "falhas", falhas, "error", status="falha"),
        ],
    }


def _where_status_grupo(canal: str, status_grupo: str) -> str | None:
    g = (status_grupo or "").strip().lower()
    if g == "entregues":
        return _STATUS_ENTREGUES_SQL
    if g == "abertos":
        return _STATUS_ABERTOS_SQL if canal == "email" else "status_ultimo IN ('lido', 'clicado')"
    return None


def _passa_filtro_pendente(claim_ativo: bool, filtro: str | None) -> bool:
    f = (filtro or "").strip().lower()
    if not f:
        return True
    if f == "claim_ativo":
        return claim_ativo
    if f == "sem_claim":
        return not claim_ativo
    return True


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


def _linha_metrica_home(chave: str, rotulo: str, valor: int, base: int) -> dict[str, Any]:
    return {
        "chave": chave,
        "rotulo": rotulo,
        "valor": int(valor),
        "percentual": _taxa_percentual(int(valor), int(base)),
    }


def _valor_etapa_funil(funil: dict[str, Any] | None, chave: str) -> int:
    if not funil:
        return 0
    for etapa in funil.get("etapas") or []:
        if etapa.get("chave") == chave:
            return int(etapa.get("valor") or 0)
    return 0


async def _count_mensagens_periodo(
    pool: PoolOrquestracao,
    tabela: str,
    inicio: date,
    fim: date,
    condicao: str = "",
) -> int:
    extra = f" AND ({condicao})" if condicao else ""
    return int(
        await pool.fetchval(
            f"""
            SELECT COUNT(*)
            FROM {tabela}
            WHERE criado_em::date BETWEEN $1 AND $2
            {extra}
            """,
            inicio,
            fim,
        )
        or 0
    )


async def _serie_mensagens_periodo(
    pool: PoolOrquestracao,
    tabela: str,
    inicio: date,
    fim: date,
    condicao: str = "",
) -> list[dict[str, Any]]:
    extra = f" AND ({condicao})" if condicao else ""
    serie = await _serie_por_dia(
        pool,
        inicio=inicio,
        fim=fim,
        sql=f"""
            SELECT criado_em::date AS ref, COUNT(*) AS total
            FROM {tabela}
            WHERE criado_em::date BETWEEN $1 AND $2
            {extra}
            GROUP BY 1
            ORDER BY 1
        """,
    )
    return _serie_resposta(inicio, fim, serie)


def _ref_dia_iso(ref: Any) -> str:
    if hasattr(ref, "isoformat"):
        return ref.isoformat()
    return str(ref)


def _preencher_series_por_dia(
    inicio: date,
    fim: date,
    rows: list[Any],
    *,
    colunas: tuple[str, ...],
) -> dict[str, dict[str, int]]:
    series = {nome: _serie_base(inicio, fim) for nome in colunas}
    for row in rows:
        chave = _ref_dia_iso(row["ref"])
        for nome in colunas:
            series[nome][chave] = int(row[nome] or 0)
    return series


async def _totais_email_periodo_home(
    pool: PoolOrquestracao,
    tabela: str,
    inicio: date,
    fim: date,
) -> dict[str, int]:
    row = await pool.fetchrow(
        f"""
        SELECT
            COUNT(*)::bigint AS total,
            COUNT(*) FILTER (
                WHERE status_ultimo IN ('lido', 'clicado')
            )::bigint AS lidos,
            COUNT(*) FILTER (
                WHERE status_ultimo = 'lido_maquina'
            )::bigint AS lidos_maquina,
            COUNT(*) FILTER (
                WHERE {_STATUS_ENTREGUES_SQL}
            )::bigint AS entregues,
            COUNT(*) FILTER (
                WHERE status_ultimo = 'clicado'
            )::bigint AS clicados,
            COUNT(*) FILTER (
                WHERE {_STATUS_FATURAVEL_SQL}
            )::bigint AS faturaveis
        FROM {tabela}
        WHERE criado_em::date BETWEEN $1 AND $2
        """,
        inicio,
        fim,
    )
    return {
        "total": int(row["total"] or 0),
        "lidos": int(row["lidos"] or 0),
        "lidos_maquina": int(row["lidos_maquina"] or 0),
        "entregues": int(row["entregues"] or 0),
        "clicados": int(row["clicados"] or 0),
        "faturaveis": int(row["faturaveis"] or 0),
    }


async def _totais_sms_periodo_home(
    pool: PoolOrquestracao,
    tabela: str,
    inicio: date,
    fim: date,
) -> dict[str, int]:
    row = await pool.fetchrow(
        f"""
        SELECT
            COUNT(*)::bigint AS total,
            COUNT(*) FILTER (
                WHERE {_SMS_ENTREGUES_SQL}
            )::bigint AS entregues,
            COUNT(*) FILTER (
                WHERE status_ultimo = 'clicado'
            )::bigint AS clicados,
            COUNT(*) FILTER (
                WHERE {_STATUS_FATURAVEL_SQL}
            )::bigint AS faturaveis
        FROM {tabela}
        WHERE criado_em::date BETWEEN $1 AND $2
        """,
        inicio,
        fim,
    )
    return {
        "total": int(row["total"] or 0),
        "entregues": int(row["entregues"] or 0),
        "clicados": int(row["clicados"] or 0),
        "faturaveis": int(row["faturaveis"] or 0),
    }


def _montar_gastos_estimados_home(
    emails_faturaveis: int,
    sms_faturaveis: int,
) -> dict[str, Any]:
    gasto_email = round(emails_faturaveis * _VALOR_UNITARIO_EMAIL_HOME, 2)
    gasto_sms = round(sms_faturaveis * _VALOR_UNITARIO_SMS_HOME, 2)
    return {
        "emails_faturaveis": int(emails_faturaveis),
        "sms_faturaveis": int(sms_faturaveis),
        "valor_unitario_email": _VALOR_UNITARIO_EMAIL_HOME,
        "valor_unitario_sms": _VALOR_UNITARIO_SMS_HOME,
        "gasto_email": gasto_email,
        "gasto_sms": gasto_sms,
        "gasto_total": round(gasto_email + gasto_sms, 2),
    }


async def _series_email_painel_por_dia(
    pool: PoolOrquestracao,
    tabela: str,
    inicio: date,
    fim: date,
) -> dict[str, dict[str, int]]:
    rows = await pool.fetch(
        f"""
        SELECT
            criado_em::date AS ref,
            COUNT(*)::bigint AS enviados,
            COUNT(*) FILTER (
                WHERE {_STATUS_ENTREGUES_SQL}
            )::bigint AS recebidos,
            COUNT(*) FILTER (
                WHERE {_STATUS_ABERTOS_SQL}
            )::bigint AS abertos,
            COUNT(*) FILTER (
                WHERE status_ultimo = 'clicado'
            )::bigint AS clicados
        FROM {tabela}
        WHERE criado_em::date BETWEEN $1 AND $2
        GROUP BY 1
        ORDER BY 1
        """,
        inicio,
        fim,
    )
    return _preencher_series_por_dia(
        inicio,
        fim,
        rows,
        colunas=("enviados", "recebidos", "abertos", "clicados"),
    )


async def _series_sms_painel_por_dia(
    pool: PoolOrquestracao,
    tabela: str,
    inicio: date,
    fim: date,
) -> dict[str, dict[str, int]]:
    rows = await pool.fetch(
        f"""
        SELECT
            criado_em::date AS ref,
            COUNT(*)::bigint AS enviados,
            COUNT(*) FILTER (
                WHERE {_SMS_RECEBIDOS_PAINEL_SQL}
            )::bigint AS recebidos,
            COUNT(*) FILTER (
                WHERE status_ultimo = 'clicado'
            )::bigint AS clicados
        FROM {tabela}
        WHERE criado_em::date BETWEEN $1 AND $2
        GROUP BY 1
        ORDER BY 1
        """,
        inicio,
        fim,
    )
    return _preencher_series_por_dia(
        inicio,
        fim,
        rows,
        colunas=("enviados", "recebidos", "clicados"),
    )


async def _pacote_email_home_periodo(
    pool: PoolOrquestracao,
    tabela: str,
    inicio: date,
    fim: date,
) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
    totais, series = await asyncio.gather(
        _totais_email_periodo_home(pool, tabela, inicio, fim),
        _series_email_painel_por_dia(pool, tabela, inicio, fim),
    )
    return totais, series


async def _pacote_sms_home_periodo(
    pool: PoolOrquestracao,
    tabela: str,
    inicio: date,
    fim: date,
) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
    totais, series = await asyncio.gather(
        _totais_sms_periodo_home(pool, tabela, inicio, fim),
        _series_sms_painel_por_dia(pool, tabela, inicio, fim),
    )
    return totais, series


def _sql_cte_convertidos_com_canal(
    *,
    teg: str,
    tf: str,
    tem: str,
    tsm: str,
    tdcf: str,
    coluna_data: str,
) -> str:
    cnpj_em = _expr_cnpj_mensagem("em")
    cnpj_sm = _expr_cnpj_mensagem("sm")
    return f"""
        WITH convertidos AS (
            SELECT
                e.cnpj_basico,
                f.{coluna_data}::date AS ref,
                EXISTS (
                    SELECT 1
                    FROM {tdcf} AS dc
                    WHERE dc.cnpj_empresa = e.cnpj_basico
                ) AS tem_contato_externo,
                (
                    SELECT MAX(em.criado_em)
                    FROM {tem} AS em
                    WHERE {cnpj_em} = e.cnpj_basico
                ) AS ultimo_email_em,
                (
                    SELECT MAX(sm.criado_em)
                    FROM {tsm} AS sm
                    WHERE {cnpj_sm} = e.cnpj_basico
                ) AS ultimo_sms_em
            FROM {teg} AS e
            INNER JOIN {tf} AS f ON f.cnpj_basico = e.cnpj_basico
            WHERE e.cadastrado_primeiro_contato = false
              AND f.{coluna_data}::date BETWEEN $1 AND $2
        ),
        com_canal AS (
            SELECT
                ref,
                tem_contato_externo,
                CASE
                    WHEN tem_contato_externo THEN NULL
                    WHEN ultimo_email_em IS NULL AND ultimo_sms_em IS NULL THEN NULL
                    WHEN ultimo_email_em IS NOT NULL AND ultimo_sms_em IS NULL THEN 'email'
                    WHEN ultimo_sms_em IS NOT NULL AND ultimo_email_em IS NULL THEN 'sms'
                    WHEN ultimo_email_em >= ultimo_sms_em THEN 'email'
                    ELSE 'sms'
                END AS canal
            FROM convertidos
        )
    """


def _preencher_series_convertidos(
    rows: list[Any],
    inicio: date,
    fim: date,
) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    serie_total = _serie_base(inicio, fim)
    serie_email = _serie_base(inicio, fim)
    serie_sms = _serie_base(inicio, fim)
    for row in rows:
        ref = row["ref"]
        chave = ref.isoformat() if hasattr(ref, "isoformat") else str(ref)
        serie_total[chave] = int(row["total"] or 0)
        serie_email[chave] = int(row["email"] or 0)
        serie_sms[chave] = int(row["sms"] or 0)
    return serie_total, serie_email, serie_sms


async def _atribuicao_convertidos_home(
    pool: PoolOrquestracao,
    *,
    teg: str,
    tf: str,
    tem: str,
    tsm: str,
    tdcf: str,
    coluna_data: str | None,
    inicio: date,
    fim: date,
) -> dict[str, Any]:
    """Contagens e séries diárias de convertidos na home (atribuição por canal)."""
    base = _serie_base(inicio, fim)
    vazio = {
        "total": 0,
        "email": 0,
        "sms": 0,
        "externo": 0,
        "sem_canal": 0,
        "serie_total": base,
        "serie_email": dict(base),
        "serie_sms": dict(base),
    }
    if not coluna_data:
        return vazio

    cte = _sql_cte_convertidos_com_canal(
        teg=teg,
        tf=tf,
        tem=tem,
        tsm=tsm,
        tdcf=tdcf,
        coluna_data=coluna_data,
    )
    rows = await pool.fetch(
        f"""
        {cte}
        SELECT
            ref,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE canal = 'email') AS email,
            COUNT(*) FILTER (WHERE canal = 'sms') AS sms,
            COUNT(*) FILTER (WHERE tem_contato_externo) AS externo,
            COUNT(*) FILTER (WHERE NOT tem_contato_externo AND canal IS NULL) AS sem_canal
        FROM com_canal
        GROUP BY ROLLUP (ref)
        ORDER BY ref NULLS FIRST
        """,
        inicio,
        fim,
    )
    total_row = rows[0] if rows else None
    daily_rows = [r for r in rows if r["ref"] is not None]
    serie_total, serie_email, serie_sms = _preencher_series_convertidos(daily_rows, inicio, fim)
    return {
        "total": int(total_row["total"] or 0) if total_row else 0,
        "email": int(total_row["email"] or 0) if total_row else 0,
        "sms": int(total_row["sms"] or 0) if total_row else 0,
        "externo": int(total_row["externo"] or 0) if total_row else 0,
        "sem_canal": int(total_row["sem_canal"] or 0) if total_row else 0,
        "serie_total": serie_total,
        "serie_email": serie_email,
        "serie_sms": serie_sms,
    }


async def _metricas_engajamento_home_periodo(
    pool: PoolOrquestracao,
    *,
    teg: str,
    te: str,
    ts: str,
    inicio: date,
    fim: date,
) -> dict[str, Any]:
    """Contatos e contatados do painel Engajamento na Home (só no período)."""
    cnpj_em = _expr_cnpj_mensagem("em")
    cnpj_sm = _expr_cnpj_mensagem("sm")

    contatos, contatados, serie_contatos, serie_contatados = await asyncio.gather(
        pool.fetchval(
            f"""
            SELECT COUNT(DISTINCT e.cnpj_basico)
            FROM {teg} AS e
            WHERE e.engajamento_atualizado_em::date BETWEEN $1 AND $2
              AND COALESCE(btrim(e.cnpj_basico), '') <> ''
            """,
            inicio,
            fim,
        ),
        pool.fetchval(
            f"""
            SELECT COUNT(DISTINCT cnpj)
            FROM (
                SELECT {cnpj_em} AS cnpj
                FROM {te} AS em
                WHERE em.criado_em::date BETWEEN $1 AND $2
                  AND {cnpj_em} <> ''
                UNION
                SELECT {cnpj_sm} AS cnpj
                FROM {ts} AS sm
                WHERE sm.criado_em::date BETWEEN $1 AND $2
                  AND {cnpj_sm} <> ''
            ) AS contatados_periodo
            """,
            inicio,
            fim,
        ),
        _serie_por_dia(
            pool,
            inicio=inicio,
            fim=fim,
            sql=f"""
                SELECT e.engajamento_atualizado_em::date AS ref, COUNT(DISTINCT e.cnpj_basico) AS total
                FROM {teg} AS e
                WHERE e.engajamento_atualizado_em::date BETWEEN $1 AND $2
                  AND COALESCE(btrim(e.cnpj_basico), '') <> ''
                GROUP BY 1
                ORDER BY 1
            """,
        ),
        _serie_por_dia(
            pool,
            inicio=inicio,
            fim=fim,
            sql=f"""
                SELECT ref, COUNT(DISTINCT cnpj) AS total
                FROM (
                    SELECT em.criado_em::date AS ref, {cnpj_em} AS cnpj
                    FROM {te} AS em
                    WHERE em.criado_em::date BETWEEN $1 AND $2
                      AND {cnpj_em} <> ''
                    UNION ALL
                    SELECT sm.criado_em::date AS ref, {cnpj_sm} AS cnpj
                    FROM {ts} AS sm
                    WHERE sm.criado_em::date BETWEEN $1 AND $2
                      AND {cnpj_sm} <> ''
                ) AS contatados_dia
                GROUP BY 1
                ORDER BY 1
            """,
        ),
    )

    return {
        "contatos": int(contatos or 0),
        "contatados": int(contatados or 0),
        "serie_contatos": serie_contatos,
        "serie_contatados": serie_contatados,
    }


async def _funil_contagens_distintas_periodo(
    pool: PoolOrquestracao,
    *,
    tabela: str,
    alias: str,
    inicio: date,
    fim: date,
    condicao_etapa2: str,
) -> tuple[int, int, int]:
    cnpj = _expr_cnpj_mensagem(alias)
    row = await pool.fetchrow(
        f"""
        SELECT
            COUNT(DISTINCT {cnpj}) FILTER (
                WHERE {cnpj} <> ''
            )::bigint AS receberam,
            COUNT(DISTINCT {cnpj}) FILTER (
                WHERE {cnpj} <> '' AND ({condicao_etapa2})
            )::bigint AS etapa2,
            COUNT(DISTINCT {cnpj}) FILTER (
                WHERE {cnpj} <> '' AND {alias}.status_ultimo = 'clicado'
            )::bigint AS clicados
        FROM {tabela} AS {alias}
        WHERE {alias}.criado_em::date BETWEEN $1 AND $2
        """,
        inicio,
        fim,
    )
    return (
        int(row["receberam"] or 0),
        int(row["etapa2"] or 0),
        int(row["clicados"] or 0),
    )


def _series_painel_prontas(
    inicio: date,
    fim: date,
    series: dict[str, dict[str, int]],
) -> dict[str, list[dict[str, Any]]]:
    return {
        chave: _serie_resposta(inicio, fim, valores)
        for chave, valores in series.items()
    }


def _painel_canal(
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


def _montar_painel_home(
    *,
    inicio: date,
    fim: date,
    total_emails: int,
    emails_entregues: int,
    emails_aberturas: int,
    emails_clicados: int,
    total_sms: int,
    sms_entregues: int,
    sms_clicados: int,
    resumo_eng: dict[str, int],
    convertidos_periodo: int,
    convertidos_email: int,
    convertidos_sms: int,
    engajamento_periodo: dict[str, Any],
    engajamento_recebidos: int,
    engajamento_engajaram: int,
    serie_emails: dict[str, int],
    serie_sms: dict[str, int],
    serie_convertidos: dict[str, int],
    serie_convertidos_email: dict[str, int],
    serie_convertidos_sms: dict[str, int],
    series_painel_email: dict[str, list[dict[str, Any]]],
    series_painel_sms: dict[str, list[dict[str, Any]]],
    emails_faturaveis: int,
    sms_faturaveis: int,
) -> dict[str, Any]:
    serie_convertidos_resp = _serie_resposta(inicio, fim, serie_convertidos)
    serie_convertidos_email_resp = _serie_resposta(inicio, fim, serie_convertidos_email)
    serie_convertidos_sms_resp = _serie_resposta(inicio, fim, serie_convertidos_sms)
    serie_emails_resp = _serie_resposta(inicio, fim, serie_emails)
    serie_sms_resp = _serie_resposta(inicio, fim, serie_sms)

    base_email = max(total_emails, 1)
    painel_email = _painel_canal(
        metrica_padrao="enviados",
        metricas=[
            _linha_metrica_home("enviados", "Enviados", total_emails, base_email),
            _linha_metrica_home("recebidos", "Recebidos", emails_entregues, base_email),
            _linha_metrica_home("abertos", "Abertos", emails_aberturas, base_email),
            _linha_metrica_home("clicados", "Clicados", emails_clicados, base_email),
            _linha_metrica_home("convertidos", "Convertidos", convertidos_email, base_email),
        ],
        series_por_metrica={
            "enviados": serie_emails_resp,
            "recebidos": series_painel_email["recebidos"],
            "abertos": series_painel_email["abertos"],
            "clicados": series_painel_email["clicados"],
            "convertidos": serie_convertidos_email_resp,
        },
    )

    base_sms = max(total_sms, 1)
    painel_sms = _painel_canal(
        metrica_padrao="enviados",
        metricas=[
            _linha_metrica_home("enviados", "Enviados", total_sms, base_sms),
            _linha_metrica_home("recebidos", "Recebidos", sms_entregues, base_sms),
            _linha_metrica_home("clicados", "Clicados", sms_clicados, base_sms),
            _linha_metrica_home("convertidos", "Convertidos", convertidos_sms, base_sms),
        ],
        series_por_metrica={
            "enviados": serie_sms_resp,
            "recebidos": series_painel_sms["recebidos"],
            "clicados": series_painel_sms["clicados"],
            "convertidos": serie_convertidos_sms_resp,
        },
    )

    contatos_eng = int(engajamento_periodo["contatos"] or 0)
    contatados_eng = int(engajamento_periodo["contatados"] or 0)
    convertidos_eng = int(engajamento_periodo["convertidos"] or 0)
    base_eng = max(contatos_eng, 1)
    recebidos_eng = int(engajamento_recebidos)
    engajaram_eng = int(engajamento_engajaram)
    serie_contatos_eng = _serie_resposta(
        inicio, fim, engajamento_periodo["serie_contatos"]
    )
    serie_contatados_eng = _serie_resposta(
        inicio, fim, engajamento_periodo["serie_contatados"]
    )
    painel_eng = _painel_canal(
        metrica_padrao="contatos",
        metricas=[
            _linha_metrica_home("contatos", "Contatos", contatos_eng, base_eng),
            _linha_metrica_home("contatados", "Contatados", contatados_eng, base_eng),
            _linha_metrica_home("recebidos", "Recebidos", recebidos_eng, base_eng),
            _linha_metrica_home("engajaram", "Engajaram", engajaram_eng, base_eng),
            _linha_metrica_home("convertidos", "Convertidos", convertidos_eng, base_eng),
        ],
        series_por_metrica={
            "contatos": serie_contatos_eng,
            "contatados": serie_contatados_eng,
            "recebidos": series_painel_email["recebidos"],
            "engajaram": series_painel_email["abertos"],
            "convertidos": serie_convertidos_resp,
        },
    )

    com_email = max(int(resumo_eng["usuarios_com_email"] or 0), 1)
    com_telefone = max(int(resumo_eng["usuarios_com_telefone"] or 0), 1)
    return {
        "email": painel_email,
        "sms": painel_sms,
        "engajamento": painel_eng,
        "gastos_estimados": _montar_gastos_estimados_home(emails_faturaveis, sms_faturaveis),
        "gauges": {
            "email": {
                "conversoes_pct": _taxa_percentual(convertidos_email, com_email),
                "cliques_pct": _taxa_percentual(emails_clicados, max(total_emails, 1)),
            },
            "sms": {
                "conversoes_pct": _taxa_percentual(convertidos_sms, com_telefone),
                "cliques_pct": _taxa_percentual(sms_clicados, max(total_sms, 1)),
            },
        },
    }


async def _coluna_data_fornecedores_cached(pool: PoolOrquestracao) -> str | None:
    global _coluna_data_fornecedor_cache
    if _coluna_data_fornecedor_cache is not False:
        return _coluna_data_fornecedor_cache  # type: ignore[return-value]
    _coluna_data_fornecedor_cache = await _coluna_data_fornecedores(pool)
    return _coluna_data_fornecedor_cache  # type: ignore[return-value]


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
    tt = p.qual("telefone_engajamento")
    tem_telefone_sms = f"""
        EXISTS (
            SELECT 1
            FROM {tt} AS t
            WHERE t.cnpj_basico = e.cnpj_basico
              AND t.canal = 'sms'
        )
    """
    row = await pool.fetchrow(
        f"""
        SELECT
            COUNT(*) AS total_monitorados,
            COUNT(*) FILTER (
                WHERE jsonb_array_length(COALESCE(contatos_email, '[]'::jsonb)) > 0
            ) AS usuarios_com_email,
            COUNT(*) FILTER (
                WHERE {tem_telefone_sms}
            ) AS usuarios_com_telefone,
            COUNT(*) FILTER (
                WHERE (
                    jsonb_array_length(COALESCE(contatos_email, '[]'::jsonb)) > 0
                    OR {tem_telefone_sms}
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
                WHERE NOT ({tem_telefone_sms})
            ) AS sms_sem_lista,
            COUNT(*) FILTER (
                WHERE {tem_telefone_sms}
                  AND lower(trim(COALESCE(e.engajamento_sms::text, ''))) = 'ativo'
            ) AS sms_agg_ativo,
            COUNT(*) FILTER (
                WHERE {tem_telefone_sms}
                  AND lower(trim(COALESCE(e.engajamento_sms::text, ''))) = 'em_analise'
            ) AS sms_agg_em_analise,
            COUNT(*) FILTER (
                WHERE {tem_telefone_sms}
                  AND lower(trim(COALESCE(e.engajamento_sms::text, ''))) = 'inativo'
            ) AS sms_agg_inativo,
            COUNT(*) FILTER (
                WHERE {tem_telefone_sms}
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
    coluna_data_fornecedor: str | None = None,
) -> dict[str, int]:
    p = obter_identificadores_postgres()
    te = p.qual("engajamento_fornecedores")
    tf = p.qual("fornecedores")
    tem = p.qual("emails_enviados")
    tsm = p.qual("sms_enviados")
    coluna_data = coluna_data_fornecedor
    if coluna_data is None:
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


def _montar_funis_home(
    *,
    resumo_eng: dict[str, int],
    email_receberam: int,
    email_lidos: int,
    email_clicados: int,
    sms_receberam: int,
    sms_entregues: int,
    sms_clicados: int,
    convertidos_email: int,
    convertidos_sms: int,
) -> dict[str, Any]:
    monitorados = int(resumo_eng["total_monitorados"] or 0)
    com_email = int(resumo_eng["usuarios_com_email"] or 0)
    com_telefone = int(resumo_eng["usuarios_com_telefone"] or 0)
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
    response: Response,
    data_inicio: date | None = None,
    data_fim: date | None = None,
) -> dict[str, Any]:
    t_inicio = time.perf_counter()
    inicio, fim = _normalizar_periodo(data_inicio, data_fim)
    p = obter_identificadores_postgres()
    te = p.qual("emails_enviados")
    ts = p.qual("sms_enviados")
    tf = p.qual("fornecedores")
    teg = p.qual("engajamento_fornecedores")

    t_pacotes = time.perf_counter()
    (
        resumo_eng,
        coluna_data_fornecedor,
        (totais_email, series_email_raw),
        (totais_sms, series_sms_raw),
    ) = await asyncio.gather(
        _resumo_engajamento(pool),
        _coluna_data_fornecedores_cached(pool),
        _pacote_email_home_periodo(pool, te, inicio, fim),
        _pacote_sms_home_periodo(pool, ts, inicio, fim),
    )
    ms_pacotes = int((time.perf_counter() - t_pacotes) * 1000)

    total_emails = totais_email["total"]
    emails_lidos = totais_email["lidos"]
    emails_lidos_maquina = totais_email["lidos_maquina"]
    emails_aberturas_total = emails_lidos + emails_lidos_maquina
    emails_entregues_home = totais_email["entregues"]
    emails_clicados_home = totais_email["clicados"]

    total_sms = totais_sms["total"]
    sms_entregues = totais_sms["entregues"]
    sms_clicados_home = totais_sms["clicados"]

    serie_emails = series_email_raw["enviados"]
    serie_sms = series_sms_raw["enviados"]
    series_painel_email = _series_painel_prontas(inicio, fim, series_email_raw)
    series_painel_sms = _series_painel_prontas(inicio, fim, series_sms_raw)

    t_paralelo = time.perf_counter()
    (
        engajamento_periodo,
        atribuicao,
        email_funil,
        sms_funil,
    ) = await asyncio.gather(
        _metricas_engajamento_home_periodo(
            pool,
            teg=teg,
            te=te,
            ts=ts,
            inicio=inicio,
            fim=fim,
        ),
        _atribuicao_convertidos_home(
            pool,
            teg=teg,
            tf=tf,
            tem=te,
            tsm=ts,
            tdcf=p.qual("whatsapp_envios"),
            coluna_data=coluna_data_fornecedor,
            inicio=inicio,
            fim=fim,
        ),
        _funil_contagens_distintas_periodo(
            pool,
            tabela=te,
            alias="m",
            inicio=inicio,
            fim=fim,
            condicao_etapa2="m.status_ultimo IN ('lido', 'clicado')",
        ),
        _funil_contagens_distintas_periodo(
            pool,
            tabela=ts,
            alias="m",
            inicio=inicio,
            fim=fim,
            condicao_etapa2="m.status_ultimo IN ('enviado', 'lido', 'clicado')",
        ),
    )
    convertidos_periodo = int(atribuicao["total"] or 0)
    convertidos_email = int(atribuicao["email"] or 0)
    convertidos_sms = int(atribuicao["sms"] or 0)
    serie_convertidos = atribuicao["serie_total"]
    serie_convertidos_email = atribuicao["serie_email"]
    serie_convertidos_sms = atribuicao["serie_sms"]
    engajamento_periodo["convertidos"] = convertidos_periodo
    engajamento_periodo["serie_convertidos"] = serie_convertidos
    email_receberam, email_lidos, email_clicados = email_funil
    sms_receberam, sms_entregues_funil, sms_clicados_funil = sms_funil
    funis = _montar_funis_home(
        resumo_eng=resumo_eng,
        email_receberam=email_receberam,
        email_lidos=email_lidos,
        email_clicados=email_clicados,
        sms_receberam=sms_receberam,
        sms_entregues=sms_entregues_funil,
        sms_clicados=sms_clicados_funil,
        convertidos_email=convertidos_email,
        convertidos_sms=convertidos_sms,
    )
    ms_paralelo = int((time.perf_counter() - t_paralelo) * 1000)

    emails_nao_lidos = max(total_emails - emails_aberturas_total, 0)
    sms_pendentes = max(total_sms - sms_entregues, 0)
    total_atribuicao = convertidos_periodo

    painel_home = _montar_painel_home(
        inicio=inicio,
        fim=fim,
        total_emails=total_emails,
        emails_entregues=emails_entregues_home,
        emails_aberturas=emails_aberturas_total,
        emails_clicados=emails_clicados_home,
        total_sms=total_sms,
        sms_entregues=sms_entregues,
        sms_clicados=sms_clicados_home,
        resumo_eng=resumo_eng,
        convertidos_periodo=convertidos_periodo,
        convertidos_email=convertidos_email,
        convertidos_sms=convertidos_sms,
        engajamento_periodo=engajamento_periodo,
        engajamento_recebidos=email_receberam,
        engajamento_engajaram=email_lidos,
        serie_emails=serie_emails,
        serie_sms=serie_sms,
        serie_convertidos=serie_convertidos,
        serie_convertidos_email=serie_convertidos_email,
        serie_convertidos_sms=serie_convertidos_sms,
        series_painel_email=series_painel_email,
        series_painel_sms=series_painel_sms,
        emails_faturaveis=int(totais_email["faturaveis"]),
        sms_faturaveis=int(totais_sms["faturaveis"]),
    )

    ms_total = int((time.perf_counter() - t_inicio) * 1000)
    response.headers["Server-Timing"] = (
        f"pacotes;dur={ms_pacotes}, "
        f"paralelo;dur={ms_paralelo}, "
        f"total;dur={ms_total}"
    )
    if _logger.isEnabledFor(logging.DEBUG):
        _logger.debug(
            "home/resumo periodo=%s..%s ms_pacotes=%s ms_paralelo=%s ms_total=%s",
            inicio,
            fim,
            ms_pacotes,
            ms_paralelo,
            ms_total,
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
                "titulo": "Conversões por canal",
                "valor": total_atribuicao,
                "total": total_atribuicao,
                "segmentos": [
                    _segmento("WhatsApp / externo", atribuicao["externo"], "success"),
                    _segmento("E-mail", convertidos_email, "info"),
                    _segmento("SMS", convertidos_sms, "warning"),
                    _segmento("Sem canal", atribuicao["sem_canal"], "neutral"),
                ],
            },
        ],
        "resumo_engajamento": resumo_eng,
        "funis": funis,
        "painel_home": painel_home,
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
    periodo_inicio: datetime | None = None,
    periodo_fim: datetime | None = None,
) -> dict[str, Any]:
    periodo = _validar_periodo_metricas(periodo_inicio, periodo_fim)
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
    _append_filtro_periodo_sql(filtros, params, periodo)
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
    filtro_pendente: str | None = None,
    periodo_inicio: datetime | None = None,
    periodo_fim: datetime | None = None,
) -> dict[str, Any]:
    periodo = _validar_periodo_metricas(periodo_inicio, periodo_fim)
    page = _page_clamped(page)
    busca = _texto(cnpj_basico)
    filtro_p = _texto(filtro_pendente)
    ids_raw = await redis.zrevrange(IDX_EMAIL_PEND, 0, -1)
    itens: list[dict[str, Any]] = []
    for ext in ids_raw:
        ext_s = ext.decode() if isinstance(ext, bytes) else str(ext)
        raw = await redis.hgetall(chave_email_pend(ext_s))
        if not raw:
            await redis.zrem(IDX_EMAIL_PEND, ext_s)
            continue
        claim = await claim_n8n_ativo(redis, canal="email", id_externo=ext_s)
        if not _passa_filtro_pendente(claim, filtro_p):
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
            "claim_n8n_ativo": claim,
        }
        if busca and busca not in str(linha.get("cnpj_basico") or ""):
            continue
        if not _linha_dentro_periodo(linha.get("criado_em"), periodo):
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
    periodo_inicio: datetime | None = None,
    periodo_fim: datetime | None = None,
) -> dict[str, Any]:
    periodo = _validar_periodo_metricas(periodo_inicio, periodo_fim)
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
        if not _linha_dentro_periodo(linha.get("criado_em"), periodo):
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
    periodo_inicio: datetime | None = None,
    periodo_fim: datetime | None = None,
) -> dict[str, Any]:
    periodo = _validar_periodo_metricas(periodo_inicio, periodo_fim)
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
    _append_filtro_periodo_sql(filtros, params, periodo)
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
    filtro_pendente: str | None = None,
    periodo_inicio: datetime | None = None,
    periodo_fim: datetime | None = None,
) -> dict[str, Any]:
    periodo = _validar_periodo_metricas(periodo_inicio, periodo_fim)
    page = _page_clamped(page)
    busca = _texto(cnpj_basico)
    filtro_p = _texto(filtro_pendente)
    ids_raw = await redis.zrevrange(IDX_SMS_PEND, 0, -1)
    itens: list[dict[str, Any]] = []
    for ext in ids_raw:
        ext_s = ext.decode() if isinstance(ext, bytes) else str(ext)
        raw = await redis.hgetall(chave_sms_pend(ext_s))
        if not raw:
            await redis.zrem(IDX_SMS_PEND, ext_s)
            continue
        claim = await claim_n8n_ativo(redis, canal="sms", id_externo=ext_s)
        if not _passa_filtro_pendente(claim, filtro_p):
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
            "claim_n8n_ativo": claim,
        }
        if busca and busca not in str(linha.get("cnpj_basico") or ""):
            continue
        if not _linha_dentro_periodo(linha.get("criado_em"), periodo):
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
    periodo_inicio: datetime | None = None,
    periodo_fim: datetime | None = None,
) -> dict[str, Any]:
    periodo = _validar_periodo_metricas(periodo_inicio, periodo_fim)
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
        if not _linha_dentro_periodo(linha.get("criado_em"), periodo):
            continue
        itens.append(enriquecer_redis_sms_esperando(linha))
    itens_pagina, total = _pagina_itens(itens, page)
    return {
        "origem": "redis",
        "tabela_logica": "sms_esperando_confirmacao",
        "itens": itens_pagina,
        **_meta(total, page),
    }


@router.get("/ligacoes/metricas")
async def metricas_ligacoes(
    pool: PoolOrquestracao,
    redis: RedisOrquestracao,
    periodo_inicio: datetime | None = None,
    periodo_fim: datetime | None = None,
) -> dict[str, Any]:
    periodo = _validar_periodo_metricas(periodo_inicio, periodo_fim)
    p = obter_identificadores_postgres()
    tl = p.qual("ligacoes_enviadas")
    total = await _pg_count_periodo(pool, tl, periodo)
    concluidos = await _pg_count_periodo(pool, tl, periodo, "status_ultimo = 'concluido'")
    sem_resposta = await _pg_count_periodo(pool, tl, periodo, "status_ultimo = 'sem_resposta'")
    falhas = await _pg_count_periodo(
        pool,
        tl,
        periodo,
        "status_ultimo IN ('falha', 'falha_definitiva')",
    )
    pendentes = await _redis_count_pendentes(redis, IDX_LIG_PEND, periodo)
    return {
        **_meta_periodo_metricas(periodo),
        "ligacoes_enviadas_total": total,
        "ligacoes_pendentes_fila": pendentes,
        "ligacoes_concluidas": concluidos,
        "ligacoes_sem_resposta": sem_resposta,
        "ligacoes_falha": falhas,
        "barra_status": _barra_status_ligacoes(total, concluidos, sem_resposta, falhas),
        "cartoes": [
            _cartao("enviadas", total, "Ligações registadas"),
            _cartao("pendentes", pendentes, "Na fila a disparar"),
            _cartao("concluidas", concluidos, "Concluídas"),
            _cartao("sem_resposta", sem_resposta, "Sem resposta"),
            _cartao("falhas", falhas, "Falha"),
        ],
    }


@router.get("/ligacoes/postgres")
async def lista_ligacoes_postgres(
    pool: PoolOrquestracao,
    page: Annotated[int, Query(ge=1)] = 1,
    status: str | None = None,
    cnpj_basico: str | None = None,
    periodo_inicio: datetime | None = None,
    periodo_fim: datetime | None = None,
) -> dict[str, Any]:
    periodo = _validar_periodo_metricas(periodo_inicio, periodo_fim)
    p = obter_identificadores_postgres()
    tl = p.qual("ligacoes_enviadas")
    page = _page_clamped(page)
    offset = (page - 1) * PAGE_SIZE

    filtros: list[str] = []
    params: list[Any] = []
    status_f = _texto(status)
    cnpj_f = _busca_cnpj(cnpj_basico)
    if status_f:
        filtros.append(f"status_ultimo = {_append_param(params, status_f)}")
    if cnpj_f:
        filtros.append(f"cnpj_basico ILIKE {_append_param(params, cnpj_f)}")
    _append_filtro_periodo_sql(filtros, params, periodo)
    where_sql = f"WHERE {' AND '.join(filtros)}" if filtros else ""

    total = int(await pool.fetchval(f"SELECT COUNT(*) FROM {tl} {where_sql}", *params) or 0)
    rows = await pool.fetch(
        f"""
        SELECT *
        FROM {tl}
        {where_sql}
        ORDER BY criado_em DESC NULLS LAST, id DESC
        LIMIT {PAGE_SIZE} OFFSET {offset}
        """,
        *params,
    )
    itens = [enriquecer_linha_postgres_ligacao(registo_para_json(r)) for r in rows]
    return {"origem": "postgres", "tabela_logica": "ligacoes_enviadas", "itens": itens, **_meta(total, page)}


@router.get("/ligacoes/redis-pendentes")
async def lista_ligacoes_redis_pendentes(
    redis: RedisOrquestracao,
    page: Annotated[int, Query(ge=1)] = 1,
    cnpj_basico: str | None = None,
    filtro_pendente: str | None = None,
    periodo_inicio: datetime | None = None,
    periodo_fim: datetime | None = None,
) -> dict[str, Any]:
    periodo = _validar_periodo_metricas(periodo_inicio, periodo_fim)
    page = _page_clamped(page)
    busca = _texto(cnpj_basico)
    filtro_p = _texto(filtro_pendente)
    ids_raw = await redis.zrevrange(IDX_LIG_PEND, 0, -1)
    itens: list[dict[str, Any]] = []
    for ext in ids_raw:
        ext_s = ext.decode() if isinstance(ext, bytes) else str(ext)
        raw = await redis.hgetall(chave_lig_pend(ext_s))
        if not raw:
            await redis.zrem(IDX_LIG_PEND, ext_s)
            continue
        claim = await claim_n8n_ativo(redis, canal="ligacao", id_externo=ext_s)
        if not _passa_filtro_pendente(claim, filtro_p):
            continue
        qtd_raw = _h(raw, "quantidade_buscas") or "0"
        try:
            qtd = int(qtd_raw)
        except ValueError:
            qtd = 0
        linha = {
            "id_externo": _h(raw, "id_externo") or ext_s,
            "telefone": _h(raw, "telefone"),
            "cnpj_basico": _h(raw, "cnpj_basico") or None,
            "quantidade_buscas": qtd,
            "uf_buscada": _h(raw, "uf_buscada") or None,
            "segmento_buscado": _h(raw, "segmento_buscado") or None,
            "nome_empresa": _h(raw, "nome_empresa") or None,
            "fornecedor_id": _h(raw, "fornecedor_id") or None,
            "origem": _h(raw, "origem"),
            "criado_em": _h(raw, "criado_em"),
            "claim_n8n_ativo": claim,
        }
        if busca and busca not in str(linha.get("cnpj_basico") or ""):
            continue
        if not _linha_dentro_periodo(linha.get("criado_em"), periodo):
            continue
        itens.append(enriquecer_redis_ligacao_pendente(linha))
    itens_pagina, total = _pagina_itens(itens, page)
    return {"origem": "redis", "tabela_logica": "ligacoes_pendentes", "itens": itens_pagina, **_meta(total, page)}


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


async def _tabela_aparicoes_disponivel(pool: PoolOrquestracao) -> bool:
    global _tabela_aparicoes_cache
    if _tabela_aparicoes_cache is not None:
        return _tabela_aparicoes_cache
    p = obter_identificadores_postgres()
    ta = p.qual("aparicoes")
    try:
        await pool.fetchval(f"SELECT 1 FROM {ta} LIMIT 1")
        _tabela_aparicoes_cache = True
    except Exception:
        _tabela_aparicoes_cache = False
    return _tabela_aparicoes_cache


def _joins_aparicoes_engajamento(p: Any, *, aparicoes_disponivel: bool) -> str:
    if not aparicoes_disponivel:
        return ""
    ta = p.qual("aparicoes")
    return f"""
        LEFT JOIN (
            SELECT cnpj_basico, COUNT(*)::int AS n
            FROM {ta}
            GROUP BY cnpj_basico
        ) AS ap_tot ON ap_tot.cnpj_basico = e.cnpj_basico
        LEFT JOIN (
            SELECT cnpj_basico, COUNT(*)::int AS n
            FROM {ta}
            WHERE created_at >= now() - interval '30 days'
            GROUP BY cnpj_basico
        ) AS ap_30 ON ap_30.cnpj_basico = e.cnpj_basico
    """


async def _contar_aparicoes_por_cnpjs(pool: PoolOrquestracao, cnpjs: list[str]) -> dict[str, int]:
    if not cnpjs:
        return {}
    if not await _tabela_aparicoes_disponivel(pool):
        return {}
    p = obter_identificadores_postgres()
    ta = p.qual("aparicoes")
    try:
        rows = await pool.fetch(
            f"""
            SELECT cnpj_basico, COUNT(*)::int AS n
            FROM {ta}
            WHERE cnpj_basico = ANY($1::text[])
            GROUP BY cnpj_basico
            """,
            cnpjs,
        )
    except Exception:
        return {}
    return {str(r["cnpj_basico"]): int(r["n"] or 0) for r in rows}


async def _contar_aparicoes_30d_por_cnpjs(pool: PoolOrquestracao, cnpjs: list[str]) -> dict[str, int]:
    if not cnpjs:
        return {}
    if not await _tabela_aparicoes_disponivel(pool):
        return {}
    p = obter_identificadores_postgres()
    ta = p.qual("aparicoes")
    try:
        rows = await pool.fetch(
            f"""
            SELECT cnpj_basico, COUNT(*)::int AS n
            FROM {ta}
            WHERE cnpj_basico = ANY($1::text[])
              AND created_at >= now() - interval '30 days'
            GROUP BY cnpj_basico
            """,
            cnpjs,
        )
    except Exception:
        return {}
    return {str(r["cnpj_basico"]): int(r["n"] or 0) for r in rows}


async def _whatsapp_resumo_por_cnpjs(pool: PoolOrquestracao, cnpjs: list[str]) -> dict[str, dict[str, Any]]:
    if not cnpjs:
        return {}
    p = obter_identificadores_postgres()
    tw = p.qual("whatsapp_envios")
    try:
        rows = await pool.fetch(
            f"""
            SELECT DISTINCT ON (cnpj_empresa)
                cnpj_empresa AS cnpj_basico,
                status,
                numero_telefone,
                whatsapp_status
            FROM {tw}
            WHERE cnpj_empresa = ANY($1::text[])
            ORDER BY cnpj_empresa, updated_at DESC NULLS LAST
            """,
            cnpjs,
        )
    except Exception:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        cnpj = str(r["cnpj_basico"])
        out[cnpj] = {
            "status": r["status"],
            "numero_telefone": r["numero_telefone"],
            "whatsapp_status": r["whatsapp_status"],
        }
    return out


async def _cadastrados_plataforma_por_cnpjs(pool: PoolOrquestracao, cnpjs: list[str]) -> set[str]:
    """CNPJs com linha em ``usuario_fornecedor`` (tabela ``fornecedores`` no schema)."""
    if not cnpjs:
        return set()
    p = obter_identificadores_postgres()
    tf = p.qual("fornecedores")
    try:
        rows = await pool.fetch(
            f"""
            SELECT DISTINCT cnpj_basico
            FROM {tf}
            WHERE cnpj_basico = ANY($1::text[])
            """,
            cnpjs,
        )
    except Exception:
        return set()
    return {str(r["cnpj_basico"]) for r in rows if r["cnpj_basico"]}


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
    ordenar: str | None = None,
) -> dict[str, Any]:
    p = obter_identificadores_postgres()
    te = p.qual("engajamento_fornecedores")
    tf = p.qual("fornecedores")
    page = _page_clamped(page)
    offset = (page - 1) * PAGE_SIZE
    orden = normalizar_ordenar_engajamento(ordenar)

    aparicoes_disponivel, col_data_fornecedor = await asyncio.gather(
        _tabela_aparicoes_disponivel(pool),
        _coluna_data_fornecedores_cached(pool),
    )

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
    filtros.extend(
        filtros_sql_por_ordenar(
            orden,
            aparicoes_disponivel=aparicoes_disponivel,
            qual_fornecedores=tf,
        ),
    )
    where_sql = f"WHERE {' AND '.join(filtros)}" if filtros else ""

    joins_sql = f"LEFT JOIN {tf} AS f ON f.cnpj_basico = e.cnpj_basico"
    joins_sql += _joins_aparicoes_engajamento(p, aparicoes_disponivel=aparicoes_disponivel)
    if orden == "cadastro_recente" and not col_data_fornecedor:
        ufid = p.col_usuario_fornecedor_id
        joins_sql += f"\nLEFT JOIN auth.users AS au ON au.id = f.{ufid}"

    from_sql = f"FROM {te} AS e\n{joins_sql}"
    order_sql = order_by_sql_engajamento(
        orden,
        aparicoes_disponivel=aparicoes_disponivel,
        col_data_fornecedor=col_data_fornecedor,
    )
    select_aparicoes = (
        f"{expr_aparicoes_total(aparicoes_disponivel=aparicoes_disponivel)} AS _aparicoes_total,"
        f"\n            {expr_aparicoes_30d(aparicoes_disponivel=aparicoes_disponivel)} AS _aparicoes_30d"
    )

    total = int(await pool.fetchval(f"SELECT COUNT(*) {from_sql} {where_sql}", *params) or 0)
    rows = await pool.fetch(
        f"""
        SELECT
            e.*,
            COALESCE(NULLIF(f.nome, ''), NULLIF(e.nome_fantasia, ''), e.cnpj_basico) AS nome_fornecedor,
            {select_aparicoes}
        {from_sql}
        {where_sql}
        ORDER BY {order_sql}
        LIMIT {PAGE_SIZE} OFFSET {offset}
        """,
        *params,
    )
    cnpjs = [str(r["cnpj_basico"]) for r in rows]
    (
        contatos_sms_por_cnpj,
        telefones_por_cnpj,
        aparicoes_por_cnpj,
        aparicoes_30d_por_cnpj,
        whatsapp_por_cnpj,
        cadastrados_plataforma,
    ) = await asyncio.gather(
        listar_contatos_sms_por_cnpjs(pool, cnpjs),
        listar_telefones_agrupados_por_cnpjs(pool, cnpjs),
        _contar_aparicoes_por_cnpjs(pool, cnpjs),
        _contar_aparicoes_30d_por_cnpjs(pool, cnpjs),
        _whatsapp_resumo_por_cnpjs(pool, cnpjs),
        _cadastrados_plataforma_por_cnpjs(pool, cnpjs),
    )
    min_aparicoes_wa = obter_configuracao().routine_min_buscas
    itens: list[dict[str, Any]] = []
    for r in rows:
        item = registo_para_json(r)
        cnpj = str(r["cnpj_basico"])
        sms_tabela = contatos_sms_por_cnpj.get(cnpj) or []
        if sms_tabela:
            item["contatos_sms"] = sms_tabela
        telefones = telefones_por_cnpj.get(cnpj) or []
        if telefones:
            item["telefones_engajamento"] = telefones
        item["aparicoes_total"] = int(
            r.get("_aparicoes_total")
            if r.get("_aparicoes_total") is not None
            else aparicoes_por_cnpj.get(cnpj, int(r.get("aparicoes_busca") or 0)),
        )
        item["aparicoes_30d"] = int(
            r.get("_aparicoes_30d")
            if r.get("_aparicoes_30d") is not None
            else aparicoes_30d_por_cnpj.get(cnpj, 0),
        )
        item["aparicoes_minimo_whatsapp"] = min_aparicoes_wa
        item["cadastrado_plataforma"] = cnpj in cadastrados_plataforma
        wa = whatsapp_por_cnpj.get(cnpj)
        if wa:
            item["whatsapp_resumo"] = wa
        itens.append(item)
    return {
        "origem": "postgres",
        "tabela_logica": "engajamento_fornecedores",
        "ordenar": orden,
        "itens": itens,
        **_meta(total, page),
    }


# WhatsApp: rotas em app/whatsapp/api/rotas/dashboard.py (whatsapp_envios)

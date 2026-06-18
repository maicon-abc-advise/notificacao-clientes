"""Persistência de ``whatsapp_envios`` — fila/funil WhatsApp."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import asyncpg

from app.config.postgres_identificadores import obter_identificadores_postgres


def _tabela() -> str:
    return obter_identificadores_postgres().qual("whatsapp_envios")


def _col_fornecedor() -> str:
    return obter_identificadores_postgres().col_fornecedor_id


def _registo_para_dict(row: asyncpg.Record) -> dict[str, Any]:
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
        elif isinstance(v, uuid.UUID):
            d[k] = str(v)
    return d


async def buscar_por_id(pool: asyncpg.Pool, envio_id: uuid.UUID | str) -> asyncpg.Record | None:
    return await pool.fetchrow(
        f"SELECT * FROM {_tabela()} WHERE id = $1 LIMIT 1",
        uuid.UUID(str(envio_id)),
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
        WHERE cnpj_basico = $1 AND numero_telefone = $2
        LIMIT 1
        """,
        cnpj_basico.strip(),
        numero_telefone.strip(),
    )


async def buscar_ultimo_por_cnpj(pool: asyncpg.Pool, cnpj_basico: str) -> asyncpg.Record | None:
    return await pool.fetchrow(
        f"""
        SELECT * FROM {_tabela()}
        WHERE cnpj_basico = $1
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
    """INSERT … ON CONFLICT DO NOTHING. Retorna (linha, inseriu)."""
    cf = _col_fornecedor()
    row = await pool.fetchrow(
        f"""
        INSERT INTO {_tabela()} (cnpj_basico, numero_telefone, {cf}, status, whatsapp_status)
        VALUES ($1, $2, $3, 'pendente', 'nao_verificado')
        ON CONFLICT (cnpj_basico, numero_telefone) DO NOTHING
        RETURNING *
        """,
        cnpj_basico.strip(),
        numero_telefone.strip(),
        fornecedor_id,
    )
    if row is not None:
        return row, True
    existente = await buscar_por_cnpj_telefone(
        pool, cnpj_basico=cnpj_basico, numero_telefone=numero_telefone
    )
    return existente, False


async def atualizar_status(
    pool: asyncpg.Pool,
    envio_id: uuid.UUID | str,
    *,
    status: str | None = None,
    whatsapp_status: str | None = None,
    motivo_falha: str | None = None,
) -> asyncpg.Record | None:
    sets: list[str] = ["updated_at = now()"]
    params: list[Any] = [uuid.UUID(str(envio_id))]
    idx = 2
    if status is not None:
        sets.append(f"status = ${idx}")
        params.append(status)
        idx += 1
    if whatsapp_status is not None:
        sets.append(f"whatsapp_status = ${idx}")
        params.append(whatsapp_status)
        idx += 1
    if motivo_falha is not None:
        sets.append(f"motivo_falha = ${idx}")
        params.append(motivo_falha)
        idx += 1
    return await pool.fetchrow(
        f"UPDATE {_tabela()} SET {', '.join(sets)} WHERE id = $1 RETURNING *",
        *params,
    )


async def incrementar_etapa_falha(
    pool: asyncpg.Pool,
    envio_id: uuid.UUID | str,
    *,
    max_falhas: int = 3,
) -> asyncpg.Record | None:
    """Incrementa próxima etapa vazia; se esgotar, ``concluido_falha``."""
    row = await buscar_por_id(pool, envio_id)
    if not row:
        return None
    etapas = [row["etapa1"], row["etapa2"], row["etapa3"]]
    n = sum(1 for e in etapas if e is not None)
    if n >= max_falhas:
        return await atualizar_status(pool, envio_id, status="concluido_falha", motivo_falha="max_falhas_conversa")
    col = f"etapa{n + 1}"
    novo_status = "pendente" if n + 1 < max_falhas else "concluido_falha"
    motivo = None if n + 1 < max_falhas else "max_falhas_conversa"
    sets = [f"{col} = now()", "updated_at = now()", f"status = ${2}"]
    params: list[Any] = [uuid.UUID(str(envio_id)), novo_status]
    if motivo:
        sets.append(f"motivo_falha = ${3}")
        params.append(motivo)
    return await pool.fetchrow(
        f"UPDATE {_tabela()} SET {', '.join(sets)} WHERE id = $1 RETURNING *",
        *params,
    )


async def listar_pendentes_para_envio(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    """Registros ``pendente`` elegíveis para 1º envio (serialização por telefone)."""
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
    """Registros ``contatado`` aguardando leitura de conversa / funil."""
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
    """Legado — união de pendentes + contatados (preferir rotinas separadas)."""
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
        out[str(r["status"])] = int(r["n"])
    return out


async def contar_whatsapp_status(pool: asyncpg.Pool) -> dict[str, int]:
    rows = await pool.fetch(
        f"""
        SELECT whatsapp_status, COUNT(*)::int AS n
        FROM {_tabela()}
        GROUP BY whatsapp_status
        """,
    )
    return {str(r["whatsapp_status"]): int(r["n"]) for r in rows}


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
        filtros.append(f"w.cnpj_basico ILIKE ${idx}")
        params.append(f"%{cnpj_basico.strip()}%")
        idx += 1
    where = f"WHERE {' AND '.join(filtros)}" if filtros else ""
    total = int(await pool.fetchval(f"SELECT COUNT(*) FROM {_tabela()} w {where}", *params) or 0)
    params.extend([limit, offset])
    rows = await pool.fetch(
        f"""
        SELECT w.*
        FROM {_tabela()} w
        {where}
        ORDER BY w.updated_at DESC, w.criado_em DESC
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
) -> uuid.UUID:
    import json

    row = await pool.fetchrow(
        f"""
        INSERT INTO {obter_identificadores_postgres().qual('whatsapp_rotina_execucoes')}
            (resultado, iniciado_em, finalizado_em)
        VALUES ($1::jsonb, $2, $3)
        RETURNING id
        """,
        json.dumps(resultado),
        iniciado_em if iniciado_em.tzinfo else iniciado_em.replace(tzinfo=UTC),
        finalizado_em if finalizado_em.tzinfo else finalizado_em.replace(tzinfo=UTC),
    )
    return row["id"]


async def listar_execucoes_rotina(pool: asyncpg.Pool, *, limit: int = 20) -> list[asyncpg.Record]:
    return await pool.fetch(
        f"""
        SELECT id, iniciado_em, finalizado_em, criado_em,
               (resultado->>'processed')::int AS processados,
               jsonb_array_length(COALESCE(resultado->'actions', '[]'::jsonb)) AS acoes
        FROM {obter_identificadores_postgres().qual('whatsapp_rotina_execucoes')}
        ORDER BY iniciado_em DESC
        LIMIT $1
        """,
        limit,
    )


async def buscar_execucao_rotina(pool: asyncpg.Pool, execucao_id: uuid.UUID | str) -> asyncpg.Record | None:
    return await pool.fetchrow(
        f"SELECT * FROM {obter_identificadores_postgres().qual('whatsapp_rotina_execucoes')} WHERE id = $1",
        uuid.UUID(str(execucao_id)),
    )

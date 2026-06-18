"""Persistência de telefones por canal em ``telefone_engajamento``."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import asyncpg

from app.config.postgres_identificadores import obter_identificadores_postgres
from app.reenvio.servicos.engajamento_contatos import (
    agora_iso,
    normalizar_telefone,
    parse_contatos_json,
)
from app.reenvio.servicos.engajamento_estado import EngajamentoSmsEstado

CANAL_SEM_CANAL = "sem_canal"
CANAL_SMS = "sms"
CANAL_WHATSAPP = "whatsapp"
CANAL_LIGACAO = "ligacao"
STATUS_SEM_STATUS = "sem_status"
CANAIS_EXIBICAO = (CANAL_SMS, CANAL_WHATSAPP, CANAL_LIGACAO)

_Executor = asyncpg.Connection | asyncpg.Pool


def _tabela() -> str:
    return obter_identificadores_postgres().qual("telefone_engajamento")


def _linha_para_contato_sms(row: asyncpg.Record) -> dict[str, Any]:
    atualizado = row["atualizado_em"]
    if isinstance(atualizado, datetime):
        ts = atualizado if atualizado.tzinfo else atualizado.replace(tzinfo=UTC)
        ultima = ts.isoformat()
    else:
        ultima = agora_iso()
    status = str(row["status"])
    if str(row["canal"]) == CANAL_SEM_CANAL:
        status = EngajamentoSmsEstado.ATIVO.value
    return {
        "endereco": str(row["telefone"]),
        "estado": status,
        "ultima_atualizacao_em": ultima,
    }


def _parse_atualizado_em(val: Any) -> datetime:
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


async def telefone_registrado(
    executor: _Executor,
    cnpj_basico: str,
    telefone: str,
) -> bool:
    cnpj = (cnpj_basico or "").strip()
    tel = normalizar_telefone(telefone)
    if not cnpj or not tel:
        return False
    val = await executor.fetchval(
        f"""
        SELECT 1
        FROM {_tabela()}
        WHERE cnpj_basico = $1 AND telefone = $2
        LIMIT 1
        """,
        cnpj,
        tel,
    )
    return val is not None


async def criar_sem_canal_se_novo(
    executor: _Executor,
    *,
    cnpj_basico: str,
    telefone: str,
    atualizado_em: datetime | None = None,
) -> bool:
    """Insere ``sem_canal`` / ``sem_status`` se o telefone ainda não existe na tabela."""
    cnpj = (cnpj_basico or "").strip()
    tel = normalizar_telefone(telefone)
    if not cnpj or not tel:
        return False
    if await telefone_registrado(executor, cnpj, tel):
        return False
    ts = atualizado_em or datetime.now(UTC)
    await executor.execute(
        f"""
        INSERT INTO {_tabela()} (cnpj_basico, telefone, canal, status, atualizado_em, criado_em)
        VALUES ($1, $2, $3, $4, $5, $5)
        """,
        cnpj,
        tel,
        CANAL_SEM_CANAL,
        STATUS_SEM_STATUS,
        ts,
    )
    return True


async def promover_ou_gravar_sms(
    executor: _Executor,
    *,
    cnpj_basico: str,
    telefone: str,
    status: str,
    atualizado_em: datetime | None = None,
) -> None:
    """
  Promove linha ``sem_canal`` para ``sms`` no 1º evento; depois atualiza ou insere linha ``sms``.
    """
    cnpj = (cnpj_basico or "").strip()
    tel = normalizar_telefone(telefone)
    if not cnpj or not tel:
        return
    ts = atualizado_em or datetime.now(UTC)

    row_sem = await executor.fetchrow(
        f"""
        SELECT canal, status
        FROM {_tabela()}
        WHERE cnpj_basico = $1 AND telefone = $2 AND canal = $3
        """,
        cnpj,
        tel,
        CANAL_SEM_CANAL,
    )
    if row_sem is not None:
        await executor.execute(
            f"""
            UPDATE {_tabela()}
            SET canal = $4, status = $5, atualizado_em = $6
            WHERE cnpj_basico = $1 AND telefone = $2 AND canal = $3
            """,
            cnpj,
            tel,
            CANAL_SEM_CANAL,
            CANAL_SMS,
            status,
            ts,
        )
        return

    await executor.execute(
        f"""
        INSERT INTO {_tabela()} (cnpj_basico, telefone, canal, status, atualizado_em, criado_em)
        VALUES ($1, $2, $3, $4, $5, $5)
        ON CONFLICT (cnpj_basico, telefone, canal) DO UPDATE SET
            status = EXCLUDED.status,
            atualizado_em = EXCLUDED.atualizado_em
        """,
        cnpj,
        tel,
        CANAL_SMS,
        status,
        ts,
    )


async def promover_ou_gravar_whatsapp(
    executor: _Executor,
    *,
    cnpj_basico: str,
    telefone: str,
    status: str,
    atualizado_em: datetime | None = None,
) -> None:
    """Promove ``sem_canal`` → ``whatsapp`` no 1º evento; depois upsert linha ``whatsapp``."""
    cnpj = (cnpj_basico or "").strip()
    tel = normalizar_telefone(telefone)
    if not cnpj or not tel:
        return
    ts = atualizado_em or datetime.now(UTC)

    row_sem = await executor.fetchrow(
        f"""
        SELECT canal, status
        FROM {_tabela()}
        WHERE cnpj_basico = $1 AND telefone = $2 AND canal = $3
        """,
        cnpj,
        tel,
        CANAL_SEM_CANAL,
    )
    if row_sem is not None:
        await executor.execute(
            f"""
            UPDATE {_tabela()}
            SET canal = $4, status = $5, atualizado_em = $6
            WHERE cnpj_basico = $1 AND telefone = $2 AND canal = $3
            """,
            cnpj,
            tel,
            CANAL_SEM_CANAL,
            CANAL_WHATSAPP,
            status,
            ts,
        )
        return

    await executor.execute(
        f"""
        INSERT INTO {_tabela()} (cnpj_basico, telefone, canal, status, atualizado_em, criado_em)
        VALUES ($1, $2, $3, $4, $5, $5)
        ON CONFLICT (cnpj_basico, telefone, canal) DO UPDATE SET
            status = EXCLUDED.status,
            atualizado_em = EXCLUDED.atualizado_em
        """,
        cnpj,
        tel,
        CANAL_WHATSAPP,
        status,
        ts,
    )


async def listar_contatos_sms_orquestracao(
    executor: _Executor,
    cnpj_basico: str,
) -> list[dict[str, Any]]:
    """Lista telefones utilizáveis no fluxo SMS (linhas ``sms`` ou ``sem_canal``)."""
    cnpj = (cnpj_basico or "").strip()
    if not cnpj:
        return []
    rows = await executor.fetch(
        f"""
        SELECT telefone, canal, status, atualizado_em
        FROM {_tabela()}
        WHERE cnpj_basico = $1 AND canal IN ($2, $3)
        ORDER BY telefone, canal
        """,
        cnpj,
        CANAL_SMS,
        CANAL_SEM_CANAL,
    )
    por_tel: dict[str, dict[str, Any]] = {}
    for row in rows:
        tel = str(row["telefone"])
        if str(row["canal"]) == CANAL_SMS:
            por_tel[tel] = _linha_para_contato_sms(row)
        elif tel not in por_tel:
            por_tel[tel] = _linha_para_contato_sms(row)
    return list(por_tel.values())


async def listar_contatos_sms(
    executor: _Executor,
    cnpj_basico: str,
) -> list[dict[str, Any]]:
    cnpj = (cnpj_basico or "").strip()
    if not cnpj:
        return []
    rows = await executor.fetch(
        f"""
        SELECT telefone, canal, status, atualizado_em
        FROM {_tabela()}
        WHERE cnpj_basico = $1 AND canal = $2
        ORDER BY telefone
        """,
        cnpj,
        CANAL_SMS,
    )
    return [_linha_para_contato_sms(r) for r in rows]


async def listar_contatos_sms_com_fallback(
    executor: _Executor,
    cnpj_basico: str,
    legado_contatos_sms: Any,
) -> list[dict[str, Any]]:
    contatos = await listar_contatos_sms_orquestracao(executor, cnpj_basico)
    if contatos:
        return contatos
    return parse_contatos_json(legado_contatos_sms)


def _agrupar_linhas_por_telefone(rows: list[asyncpg.Record]) -> list[dict[str, Any]]:
    por_tel: dict[str, dict[str, Any]] = {}
    for row in rows:
        tel = str(row["telefone"])
        canal = str(row["canal"])
        if canal == CANAL_SEM_CANAL:
            if tel not in por_tel:
                por_tel[tel] = {"telefone": tel, "canais": {}}
            continue
        if canal not in CANAIS_EXIBICAO:
            continue
        bloco = por_tel.setdefault(tel, {"telefone": tel, "canais": {}})
        atualizado = row["atualizado_em"]
        if isinstance(atualizado, datetime):
            ts = atualizado if atualizado.tzinfo else atualizado.replace(tzinfo=UTC)
            atualizado_iso = ts.isoformat()
        else:
            atualizado_iso = None
        bloco["canais"][canal] = {
            "canal": canal,
            "status": str(row["status"]),
            "atualizado_em": atualizado_iso,
        }

    saida: list[dict[str, Any]] = []
    for tel in sorted(por_tel.keys()):
        bloco = por_tel[tel]
        canais_map: dict[str, dict[str, Any] | None] = bloco["canais"]
        canais_lista: list[dict[str, Any] | None] = []
        for canal in CANAIS_EXIBICAO:
            canais_lista.append(canais_map.get(canal))
        saida.append({"telefone": tel, "canais": canais_lista})
    return saida


async def listar_telefones_agrupados(
    executor: _Executor,
    cnpj_basico: str,
) -> list[dict[str, Any]]:
    cnpj = (cnpj_basico or "").strip()
    if not cnpj:
        return []
    rows = await executor.fetch(
        f"""
        SELECT telefone, canal, status, atualizado_em
        FROM {_tabela()}
        WHERE cnpj_basico = $1
        ORDER BY telefone, canal
        """,
        cnpj,
    )
    return _agrupar_linhas_por_telefone(list(rows))


async def listar_telefones_agrupados_por_cnpjs(
    executor: _Executor,
    cnpjs: list[str],
) -> dict[str, list[dict[str, Any]]]:
    chaves = [(c or "").strip() for c in cnpjs if (c or "").strip()]
    if not chaves:
        return {}
    rows = await executor.fetch(
        f"""
        SELECT cnpj_basico, telefone, canal, status, atualizado_em
        FROM {_tabela()}
        WHERE cnpj_basico = ANY($1::text[])
        ORDER BY cnpj_basico, telefone, canal
        """,
        chaves,
    )
    por_cnpj: dict[str, list[asyncpg.Record]] = {c: [] for c in chaves}
    for row in rows:
        cnpj = str(row["cnpj_basico"])
        por_cnpj.setdefault(cnpj, []).append(row)
    return {cnpj: _agrupar_linhas_por_telefone(linhas) for cnpj, linhas in por_cnpj.items()}


async def listar_contatos_sms_por_cnpjs(
    executor: _Executor,
    cnpjs: list[str],
) -> dict[str, list[dict[str, Any]]]:
    """Compatível com listagem resumida (somente linhas ``sms``)."""
    chaves = [(c or "").strip() for c in cnpjs if (c or "").strip()]
    if not chaves:
        return {}
    rows = await executor.fetch(
        f"""
        SELECT cnpj_basico, telefone, canal, status, atualizado_em
        FROM {_tabela()}
        WHERE canal = $1
          AND cnpj_basico = ANY($2::text[])
        ORDER BY cnpj_basico, telefone
        """,
        CANAL_SMS,
        chaves,
    )
    out: dict[str, list[dict[str, Any]]] = {c: [] for c in chaves}
    for row in rows:
        cnpj = str(row["cnpj_basico"])
        out.setdefault(cnpj, []).append(_linha_para_contato_sms(row))
    return out


async def telefone_sms_existe(
    executor: _Executor,
    cnpj_basico: str,
    telefone: str,
) -> bool:
    return await telefone_registrado(executor, cnpj_basico, telefone)


async def fundir_telefones_descobertos(
    executor: _Executor,
    *,
    cnpj_basico: str,
    novos: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Registra telefones novos com ``sem_canal`` / ``sem_status``; não altera canais existentes."""
    cnpj = (cnpj_basico or "").strip()
    if not cnpj:
        return []
    for contato in novos:
        tel = normalizar_telefone(str(contato.get("endereco") or ""))
        if not tel:
            continue
        atualizado_em = _parse_atualizado_em(contato.get("ultima_atualizacao_em"))
        await criar_sem_canal_se_novo(
            executor,
            cnpj_basico=cnpj,
            telefone=tel,
            atualizado_em=atualizado_em,
        )
    return await listar_contatos_sms_orquestracao(executor, cnpj)


async def garantir_telefone_descoberto(
    executor: _Executor,
    *,
    cnpj_basico: str,
    telefone: str,
    now_iso: str | None = None,
) -> None:
    await criar_sem_canal_se_novo(
        executor,
        cnpj_basico=cnpj_basico,
        telefone=telefone,
        atualizado_em=_parse_atualizado_em(now_iso or agora_iso()),
    )

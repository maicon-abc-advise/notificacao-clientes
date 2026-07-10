from __future__ import annotations

import asyncpg

from app.config.postgres_identificadores import obter_identificadores_postgres
from app.config.variaveis_sistema.modelo import TipoVariavelSistema, VariavelSistemaRegistro


def _tabela() -> str:
    return obter_identificadores_postgres().qual("variaveis_sistema")


def _row_para_registro(row: asyncpg.Record) -> VariavelSistemaRegistro:
    return VariavelSistemaRegistro(
        chave=str(row["chave"]),
        valor=str(row["valor"]),
        tipo=TipoVariavelSistema(str(row["tipo"])),
        grupo=str(row["grupo"]),
        descricao=str(row["descricao"] or ""),
        editavel=bool(row["editavel"]),
    )


async def listar_todas(pool: asyncpg.Pool) -> list[VariavelSistemaRegistro]:
    rows = await pool.fetch(
        f"""
        SELECT chave, valor, tipo, grupo, descricao, editavel
        FROM {_tabela()}
        ORDER BY grupo, chave
        """
    )
    return [_row_para_registro(r) for r in rows]


async def buscar_por_chave(pool: asyncpg.Pool, chave: str) -> VariavelSistemaRegistro | None:
    row = await pool.fetchrow(
        f"""
        SELECT chave, valor, tipo, grupo, descricao, editavel
        FROM {_tabela()}
        WHERE chave = $1
        """,
        chave.strip(),
    )
    if not row:
        return None
    return _row_para_registro(row)


async def atualizar_valor(pool: asyncpg.Pool, chave: str, valor: str) -> VariavelSistemaRegistro | None:
    row = await pool.fetchrow(
        f"""
        UPDATE {_tabela()}
        SET valor = $2, atualizado_em = now()
        WHERE chave = $1
        RETURNING chave, valor, tipo, grupo, descricao, editavel
        """,
        chave.strip(),
        valor,
    )
    if not row:
        return None
    return _row_para_registro(row)


async def mapa_valores(pool: asyncpg.Pool) -> dict[str, str]:
    rows = await pool.fetch(f"SELECT chave, valor FROM {_tabela()}")
    return {str(r["chave"]): str(r["valor"]) for r in rows}

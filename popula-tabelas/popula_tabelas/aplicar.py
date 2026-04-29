"""Aplicação de SQL e seed no Postgres (ambiente de desenvolvimento / testes)."""

from __future__ import annotations

from pathlib import Path

import asyncpg

from popula_tabelas.dados_seed import linhas_seed

_DIR_SQL = Path(__file__).resolve().parent / "sql"


async def aplicar_schema_templates(dsn: str) -> None:
    schema = (_DIR_SQL / "templates_notificacao.sql").read_text(encoding="utf-8")
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(schema)
    finally:
        await conn.close()


async def aplicar_seed_templates(dsn: str) -> None:
    sql = """
    INSERT INTO public.templates_notificacao (id, tipo, email, sms)
    VALUES ($1, $2, $3, $4)
    ON CONFLICT (tipo) DO UPDATE SET
        id = EXCLUDED.id,
        email = EXCLUDED.email,
        sms = EXCLUDED.sms
    """
    conn = await asyncpg.connect(dsn)
    try:
        for id_, tipo, email, sms in linhas_seed():
            await conn.execute(sql, id_, tipo, email, sms)
    finally:
        await conn.close()


async def aplicar_templates_schema_e_seed(dsn: str) -> None:
    await aplicar_schema_templates(dsn)
    await aplicar_seed_templates(dsn)


async def aplicar_schema_reenvio(dsn: str) -> None:
    sql = (_DIR_SQL / "reenvio.sql").read_text(encoding="utf-8")
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


async def aplicar_schema_orquestracao(dsn: str) -> None:
    sql = (_DIR_SQL / "orquestracao_consultas_fornecedores.sql").read_text(encoding="utf-8")
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


async def aplicar_tudo(dsn: str) -> None:
    """Ordem: templates (tabela + linhas), tabelas de reenvio, tabelas de orquestração."""
    await aplicar_templates_schema_e_seed(dsn)
    await aplicar_schema_reenvio(dsn)
    await aplicar_schema_orquestracao(dsn)

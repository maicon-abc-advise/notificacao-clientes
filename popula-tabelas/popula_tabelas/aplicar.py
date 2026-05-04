"""Aplicação de SQL e seed no Postgres (ambiente de desenvolvimento / testes)."""

from __future__ import annotations

from pathlib import Path

import asyncpg

from app.config.postgres_identificadores import obter_identificadores_postgres, substituir_sql_ddl
from popula_tabelas.dados_seed import linhas_seed

_DIR_SQL = Path(__file__).resolve().parent / "sql"

# Migrações só com DDL idempotente (preserva linhas existentes). Ordem importa.
_MIGRACOES_ORQUESTRACAO_INCREMENTAIS: tuple[str, ...] = (
    "orquestracao_fornecedores_creditos.sql",
    "migracao_engajamento_fornecedor_id.sql",
)

def _sql_arquivo(nome: str) -> str:
    raw = (_DIR_SQL / nome).read_text(encoding="utf-8")
    return substituir_sql_ddl(raw, obter_identificadores_postgres())

async def aplicar_migracoes_orquestracao_incrementais(dsn: str) -> None:
    """Apenas ALTER/ADD seguros em orquestração — não recria tabelas nem roda seed."""
    conn = await asyncpg.connect(dsn)
    try:
        for nome in _MIGRACOES_ORQUESTRACAO_INCREMENTAIS:
            await conn.execute(_sql_arquivo(nome))
    finally:
        await conn.close()


async def aplicar_schema_templates(dsn: str) -> None:
    schema = _sql_arquivo("templates_notificacao.sql")
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(schema)
    finally:
        await conn.close()


async def aplicar_seed_templates(dsn: str) -> None:
    p = obter_identificadores_postgres()
    tt = p.qual("templates_notificacao")
    sql = f"""
    INSERT INTO {tt} (id, tipo, email, sms)
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


async def _migrar_status_ultimo_lido_e_limpar_zenvia(conn: asyncpg.Connection) -> None:
    """Remove coluna legada ``zenvia_ultimo_code`` e alinha CHECK de ``status_ultimo`` com valor ``lido``."""
    p = obter_identificadores_postgres()
    for base, chk in (
        ("emails_enviados", "emails_enviados_status_chk"),
        ("sms_enviados", "sms_enviados_status_chk"),
    ):
        t = p.qual(base)
        await conn.execute(f"ALTER TABLE {t} DROP COLUMN IF EXISTS zenvia_ultimo_code")
        await conn.execute(f"ALTER TABLE {t} DROP CONSTRAINT IF EXISTS {chk}")
        await conn.execute(
            f"""ALTER TABLE {t} ADD CONSTRAINT {chk} CHECK (
                status_ultimo IN ('processando', 'enviado', 'lido', 'falha_definitiva', 'reprocessar')
            )""",
        )


async def aplicar_schema_reenvio(dsn: str) -> None:
    sql = _sql_arquivo("reenvio.sql")
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(sql)
        await _migrar_status_ultimo_lido_e_limpar_zenvia(conn)
    finally:
        await conn.close()


async def aplicar_schema_orquestracao(dsn: str) -> None:
    principal = _sql_arquivo("orquestracao_consultas_fornecedores.sql")
    creditos = _sql_arquivo("orquestracao_fornecedores_creditos.sql")
    migracao = _sql_arquivo("migracao_engajamento_fornecedor_id.sql")
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(principal)
        await conn.execute(creditos)
        await conn.execute(migracao)
    finally:
        await conn.close()


async def aplicar_tudo(dsn: str) -> None:
    """Ordem: templates (tabela + linhas), tabelas de reenvio, tabelas de orquestração."""
    await aplicar_templates_schema_e_seed(dsn)
    await aplicar_schema_reenvio(dsn)
    await aplicar_schema_orquestracao(dsn)

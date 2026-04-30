"""Nomes qualificados de schema/tabela/coluna para Postgres (sufixo só em consultas/fornecedores + coluna FK)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from app.config.config import obter_configuracao


def _q_ident(ident: str) -> str:
    if re.match(r"^[a-z_][a-z0-9_]*$", ident):
        return ident
    return '"' + ident.replace('"', '""') + '"'


@dataclass(frozen=True, slots=True)
class PostgresIdentificadores:
    """Alinhado a POSTGRES_SCHEMA e POSTGRES_TABELA_SUFFIX no .env."""

    schema: str
    tabela_suffix: str

    @property
    def col_fornecedor_id(self) -> str:
        if not self.tabela_suffix:
            return "fornecedor_id"
        return f"fornecedor_id{self.tabela_suffix}"

    def nome_fisico_tabela(self, base: str) -> str:
        if base in ("consultas", "fornecedores"):
            return base + self.tabela_suffix
        return base

    def qual(self, base: str) -> str:
        return f"{_q_ident(self.schema)}.{_q_ident(self.nome_fisico_tabela(base))}"


_RE_FID = re.compile(r"\bfornecedor_id\b")


def substituir_sql_ddl(sql: str, p: PostgresIdentificadores) -> str:
    """Ajusta DDL/arquivos .sql: schema, tabelas consultas/fornecedores e coluna fornecedor_id."""
    s = sql
    s = s.replace("public.fornecedores", p.qual("fornecedores"))
    s = s.replace("public.consultas", p.qual("consultas"))
    if p.schema != "public":
        s = s.replace("public.", f"{_q_ident(p.schema)}.")
    if p.tabela_suffix:
        s = _RE_FID.sub(p.col_fornecedor_id, s)
    return s


@lru_cache
def obter_identificadores_postgres() -> PostgresIdentificadores:
    c = obter_configuracao()
    sch = (c.postgres_schema or "public").strip() or "public"
    suf = (c.postgres_tabela_suffix or "").strip()
    return PostgresIdentificadores(schema=sch, tabela_suffix=suf)

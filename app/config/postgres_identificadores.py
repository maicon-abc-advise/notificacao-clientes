from __future__ import annotations
import re
from dataclasses import dataclass
from functools import lru_cache
from app.config.config import obter_configuracao

_RE_FID = re.compile(r"\bfornecedor_id\b")
_RE_PUBLIC_UF = re.compile(r"public\.usuario_fornecedor\b(?![a-z0-9_])")

def _q_ident(ident: str) -> str:
    if re.match(r"^[a-z_][a-z0-9_]*$", ident):
        return ident
    return '"' + ident.replace('"', '""') + '"'

@dataclass(frozen=True, slots=True)
class PostgresIdentificadores:

    schema: str
    tabela_suffix: str

    @property
    def col_fornecedor_id(self) -> str:
        if not self.tabela_suffix:
            return "fornecedor_id"
        return f"fornecedor_id{self.tabela_suffix}"

    @property
    def col_usuario_fornecedor_id(self) -> str:
        return "id"

    def nome_fisico_tabela(self, base: str) -> str:
        if base == "fornecedores":
            return "usuario_fornecedor" + self.tabela_suffix
        if base == "consultas":
            return base + self.tabela_suffix
        return base

    def qual(self, base: str) -> str:
        return f"{_q_ident(self.schema)}.{_q_ident(self.nome_fisico_tabela(base))}"

def substituir_sql_ddl(sql: str, p: PostgresIdentificadores) -> str:
    s = sql
    s = s.replace("public.fornecedores", p.qual("fornecedores"))
    s = _RE_PUBLIC_UF.sub(p.qual("fornecedores"), s)
    s = s.replace("public.consultas", p.qual("consultas"))
    if p.schema != "public":
        s = s.replace("public.", f"{_q_ident(p.schema)}.")
    if p.tabela_suffix:
        s = _RE_FID.sub(p.col_fornecedor_id, s)
    # Em usuario_fornecedor a PK é sempre ``id``; não ``fornecedor_id``/sufixo.
    qf = p.qual("fornecedores")
    cf = p.col_fornecedor_id
    cid = p.col_usuario_fornecedor_id
    for a, b in (
        (f"{qf} ({cf})", f"{qf} ({cid})"),
        (f"{qf}({cf})", f"{qf}({cid})"),
    ):
        s = s.replace(a, b)
    return s

@lru_cache
def obter_identificadores_postgres() -> PostgresIdentificadores:
    c = obter_configuracao()
    sch = (c.postgres_schema or "public").strip() or "public"
    suf = (c.postgres_tabela_suffix or "").strip()
    return PostgresIdentificadores(schema=sch, tabela_suffix=suf)
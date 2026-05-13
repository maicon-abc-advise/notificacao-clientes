"""Mutações (PATCH/DELETE) para o dashboard: Postgres e Redis."""

from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime
from typing import Any

import asyncpg
from fastapi import HTTPException
from redis.asyncio import Redis

from app.config.postgres_identificadores import obter_identificadores_postgres
from app.dashboard.servicos.exibicao import (
    enriquecer_linha_postgres,
    enriquecer_redis_email_esperando,
    enriquecer_redis_email_pendente,
    enriquecer_redis_sms_esperando,
    enriquecer_redis_sms_pendente,
)
from app.dashboard.servicos.serializacao import decodificar_contexto_json_bruto, registo_para_json
from app.iam.dashboard.dashboard_auth import validar_login
from app.orquestracao.repositorios.redis_emails_pendentes_repo import (
    RepositorioEmailsPendenteRedis,
    chave_hash as chave_email_pend_hash,
)
from app.reenvio.repositorios.redis_emails_esperando_confirmacao import (
    RepositorioEmailsEsperandoConfirmacaoRedis,
    chave_hash as chave_email_esp_hash,
)
from app.reenvio.repositorios.redis_sms_esperando_confirmacao import (
    RepositorioSmsEsperandoConfirmacaoRedis,
    chave_hash as chave_sms_esp_hash,
)
from app.reenvio.repositorios.redis_sms_pendente import RepositorioSmsPendenteRedis, chave_hash as chave_sms_pend_hash

_repo_email_pend = RepositorioEmailsPendenteRedis()
_repo_email_esp = RepositorioEmailsEsperandoConfirmacaoRedis()
_repo_sms_pend = RepositorioSmsPendenteRedis()
_repo_sms_esp = RepositorioSmsEsperandoConfirmacaoRedis()


def _q_col(ident: str) -> str:
    if re.match(r"^[a-z_][a-z0-9_]*$", ident, re.I):
        return ident
    return '"' + ident.replace('"', '""') + '"'


def _exigir_senha(sessao: dict[str, Any], senha: str) -> None:
    login = str(sessao.get("login") or "")
    if not validar_login(login, senha):
        raise HTTPException(status_code=401, detail="Senha inválida")


async def _colunas_tabela(pool: asyncpg.Pool, schema: str, table: str) -> dict[str, str]:
    rows = await pool.fetch(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = $1 AND table_name = $2
        """,
        schema,
        table,
    )
    return {str(r["column_name"]): str(r["data_type"]) for r in rows}


def _valor_sql_param(col: str, v: Any, data_type: str) -> Any:
    if data_type in ("jsonb", "json"):
        if isinstance(v, str):
            return v
        return json.dumps(v, ensure_ascii=False)
    if data_type == "uuid":
        if v is None or v == "":
            return None
        return uuid.UUID(str(v))
    if data_type in ("integer", "bigint", "smallint"):
        return int(v)
    if data_type == "boolean":
        if isinstance(v, bool):
            return v
        s = str(v).strip().lower()
        if s in ("true", "1", "sim", "yes"):
            return True
        if s in ("false", "0", "nao", "não", "no"):
            return False
        raise HTTPException(status_code=400, detail=f"Boolean inválido em {col}")
    if data_type.startswith("timestamp"):
        if isinstance(v, (datetime, date)):
            return v
        return v
    return v


async def patch_postgres_tabela(
    pool: asyncpg.Pool,
    *,
    tabela_logica: str,
    pk_coluna: str,
    pk_valor: Any,
    body: dict[str, Any],
    bloqueadas: set[str],
    canal_enriquecer: str | None,
) -> dict[str, Any]:
    if not body:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    p = obter_identificadores_postgres()
    nome_fis = p.nome_fisico_tabela(tabela_logica)
    tabela_ql = p.qual(tabela_logica)
    colunas = await _colunas_tabela(pool, p.schema, nome_fis)
    if not colunas:
        raise HTTPException(status_code=503, detail="Tabela não encontrada no schema")

    sets: list[str] = []
    params: list[Any] = []
    for chave, valor in body.items():
        if chave in bloqueadas:
            raise HTTPException(status_code=400, detail=f"Campo não editável: {chave}")
        if chave not in colunas:
            raise HTTPException(status_code=400, detail=f"Campo desconhecido: {chave}")
        params.append(_valor_sql_param(chave, valor, colunas[chave]))
        n = len(params)
        if colunas[chave] in ("jsonb", "json"):
            sets.append(f"{_q_col(chave)} = ${n}::jsonb")
        else:
            sets.append(f"{_q_col(chave)} = ${n}")

    params.append(pk_valor)
    wh = f"{_q_col(pk_coluna)} = ${len(params)}"
    sql = f"UPDATE {tabela_ql} SET {', '.join(sets)} WHERE {wh} RETURNING *"
    row = await pool.fetchrow(sql, *params)
    if not row:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    item = registo_para_json(row)
    if canal_enriquecer in ("email", "sms"):
        return enriquecer_linha_postgres(item, canal=canal_enriquecer)
    return item


async def delete_postgres_tabela(
    pool: asyncpg.Pool,
    *,
    tabela_logica: str,
    pk_coluna: str,
    pk_valor: Any,
    sessao: dict[str, Any],
    senha: str,
) -> None:
    _exigir_senha(sessao, senha)
    p = obter_identificadores_postgres()
    tabela_ql = p.qual(tabela_logica)
    row = await pool.fetchrow(
        f"DELETE FROM {tabela_ql} WHERE {_q_col(pk_coluna)} = $1 RETURNING {_q_col(pk_coluna)}",
        pk_valor,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Registro não encontrado")


def _str_redis(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def _montar_patch_redis_hash(body: dict[str, Any], *, permitidas: set[str], bloqueadas: set[str]) -> dict[str, str]:
    if not body:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    out: dict[str, str] = {}
    for k, v in body.items():
        if k in bloqueadas:
            raise HTTPException(status_code=400, detail=f"Campo não editável: {k}")
        if k == "contexto":
            out["contexto_json"] = _str_redis(v)
            continue
        if k not in permitidas:
            raise HTTPException(status_code=400, detail=f"Campo não permitido: {k}")
        out[k] = _str_redis(v)
    return out


_WHITELIST_EMAIL_PEND = {
    "destinatario",
    "tipo_template",
    "contexto",
    "remetente",
    "fornecedor_id",
    "cnpj_basico",
    "origem",
    "consulta_id",
    "criado_em",
}
_BLOCK_EMAIL_PEND = {"id_externo", "external_id", "message_id_zenvia"}

_WHITELIST_EMAIL_ESP = {
    "email_destinatario",
    "tipo_template",
    "contexto",
    "remetente",
    "fornecedor_id",
    "cnpj_basico",
    "consulta_id",
    "status_atual",
    "criado_em",
    "atualizado_em",
    "ultimo_cause",
}
_BLOCK_EMAIL_ESP = {"message_id_zenvia", "id_externo", "external_id"}


_WHITELIST_SMS_PEND = {
    "telefone",
    "tipo_template",
    "contexto",
    "remetente",
    "origem",
    "fornecedor_id",
    "cnpj_basico",
    "consulta_id",
    "criado_em",
}
_BLOCK_SMS_PEND = {"id_externo", "external_id", "message_id_zenvia"}

_WHITELIST_SMS_ESP = {
    "telefone_destinatario",
    "tipo_template",
    "contexto",
    "remetente",
    "fornecedor_id",
    "cnpj_basico",
    "consulta_id",
    "status_atual",
    "criado_em",
    "atualizado_em",
}
_BLOCK_SMS_ESP = {"message_id_zenvia", "id_externo", "external_id"}


def _redis_h(raw: dict[Any, Any], key: str) -> str | None:
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


async def _linha_email_pendente_apos_patch(redis: Redis, id_externo: str) -> dict[str, Any]:
    raw = await redis.hgetall(chave_email_pend_hash(id_externo))
    if not raw:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    ext_s = id_externo
    ctx = decodificar_contexto_json_bruto(_redis_h(raw, "contexto_json"))
    linha: dict[str, Any] = {
        "id_externo": _redis_h(raw, "id_externo") or _redis_h(raw, "external_id") or ext_s,
        "destinatario": _redis_h(raw, "destinatario"),
        "tipo_template": _redis_h(raw, "tipo_template"),
        "contexto": ctx if isinstance(ctx, dict) else {},
        "remetente": _redis_h(raw, "remetente") or None,
        "fornecedor_id": _redis_h(raw, "fornecedor_id") or _redis_h(raw, "usuario_id") or None,
        "cnpj_basico": _redis_h(raw, "cnpj_basico") or None,
        "origem": _redis_h(raw, "origem"),
        "consulta_id": _redis_h(raw, "consulta_id") or None,
        "criado_em": _redis_h(raw, "criado_em"),
    }
    return enriquecer_redis_email_pendente(linha)


async def _linha_email_esperando_apos_patch(redis: Redis, message_id: str) -> dict[str, Any]:
    raw = await redis.hgetall(chave_email_esp_hash(message_id))
    if not raw:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    ctx = decodificar_contexto_json_bruto(_redis_h(raw, "contexto_json"))
    linha = {
        "message_id_zenvia": message_id,
        "id_externo": _redis_h(raw, "id_externo") or _redis_h(raw, "external_id"),
        "email_destinatario": _redis_h(raw, "email_destinatario"),
        "tipo_template": _redis_h(raw, "tipo_template"),
        "contexto": ctx if isinstance(ctx, dict) else {},
        "remetente": _redis_h(raw, "remetente") or None,
        "fornecedor_id": _redis_h(raw, "fornecedor_id") or _redis_h(raw, "usuario_id") or None,
        "cnpj_basico": _redis_h(raw, "cnpj_basico") or None,
        "consulta_id": _redis_h(raw, "consulta_id") or None,
        "status_atual": _redis_h(raw, "status_atual"),
        "criado_em": _redis_h(raw, "criado_em"),
        "atualizado_em": _redis_h(raw, "atualizado_em"),
        "ultimo_cause": _redis_h(raw, "ultimo_cause"),
    }
    return enriquecer_redis_email_esperando(linha)


async def _linha_sms_pendente_apos_patch(redis: Redis, id_externo: str) -> dict[str, Any]:
    raw = await redis.hgetall(chave_sms_pend_hash(id_externo))
    if not raw:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    ext_s = id_externo
    ctx = decodificar_contexto_json_bruto(_redis_h(raw, "contexto_json"))
    linha = {
        "id_externo": _redis_h(raw, "id_externo") or _redis_h(raw, "external_id") or ext_s,
        "telefone": _redis_h(raw, "telefone"),
        "tipo_template": _redis_h(raw, "tipo_template"),
        "contexto": ctx if isinstance(ctx, dict) else {},
        "remetente": _redis_h(raw, "remetente") or None,
        "origem": _redis_h(raw, "origem"),
        "fornecedor_id": _redis_h(raw, "fornecedor_id") or _redis_h(raw, "usuario_id") or None,
        "cnpj_basico": _redis_h(raw, "cnpj_basico") or None,
        "consulta_id": _redis_h(raw, "consulta_id") or None,
        "criado_em": _redis_h(raw, "criado_em"),
    }
    return enriquecer_redis_sms_pendente(linha)


async def _linha_sms_esperando_apos_patch(redis: Redis, message_id: str) -> dict[str, Any]:
    raw = await redis.hgetall(chave_sms_esp_hash(message_id))
    if not raw:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    ctx = decodificar_contexto_json_bruto(_redis_h(raw, "contexto_json"))
    linha = {
        "message_id_zenvia": message_id,
        "id_externo": _redis_h(raw, "id_externo") or _redis_h(raw, "external_id"),
        "telefone_destinatario": _redis_h(raw, "telefone_destinatario"),
        "tipo_template": _redis_h(raw, "tipo_template"),
        "contexto": ctx if isinstance(ctx, dict) else {},
        "remetente": _redis_h(raw, "remetente") or None,
        "fornecedor_id": _redis_h(raw, "fornecedor_id") or _redis_h(raw, "usuario_id") or None,
        "cnpj_basico": _redis_h(raw, "cnpj_basico") or None,
        "consulta_id": _redis_h(raw, "consulta_id") or None,
        "status_atual": _redis_h(raw, "status_atual"),
        "criado_em": _redis_h(raw, "criado_em"),
        "atualizado_em": _redis_h(raw, "atualizado_em"),
    }
    return enriquecer_redis_sms_esperando(linha)


async def patch_redis_email_pendente(redis: Redis, id_externo: str, body: dict[str, Any]) -> dict[str, Any]:
    mapping = _montar_patch_redis_hash(body, permitidas=_WHITELIST_EMAIL_PEND, bloqueadas=_BLOCK_EMAIL_PEND)
    ok = await _repo_email_pend.atualizar_campos(redis, id_externo, mapping)
    if not ok:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    return await _linha_email_pendente_apos_patch(redis, id_externo)


async def delete_redis_email_pendente(
    redis: Redis, id_externo: str, sessao: dict[str, Any], senha: str
) -> None:
    _exigir_senha(sessao, senha)
    if not await redis.exists(chave_email_pend_hash(id_externo)):
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    await _repo_email_pend.remover(redis, id_externo)


async def patch_redis_email_esperando(redis: Redis, message_id: str, body: dict[str, Any]) -> dict[str, Any]:
    mapping = _montar_patch_redis_hash(body, permitidas=_WHITELIST_EMAIL_ESP, bloqueadas=_BLOCK_EMAIL_ESP)
    if not await redis.exists(chave_email_esp_hash(message_id)):
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    await _repo_email_esp.atualizar_campos(redis, message_id, mapping)
    return await _linha_email_esperando_apos_patch(redis, message_id)


async def delete_redis_email_esperando(
    redis: Redis, message_id: str, sessao: dict[str, Any], senha: str
) -> None:
    _exigir_senha(sessao, senha)
    if not await redis.exists(chave_email_esp_hash(message_id)):
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    await _repo_email_esp.remover(redis, message_id)


async def patch_redis_sms_pendente(redis: Redis, id_externo: str, body: dict[str, Any]) -> dict[str, Any]:
    mapping = _montar_patch_redis_hash(body, permitidas=_WHITELIST_SMS_PEND, bloqueadas=_BLOCK_SMS_PEND)
    ok = await _repo_sms_pend.atualizar_campos(redis, id_externo, mapping)
    if not ok:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    return await _linha_sms_pendente_apos_patch(redis, id_externo)


async def delete_redis_sms_pendente(redis: Redis, id_externo: str, sessao: dict[str, Any], senha: str) -> None:
    _exigir_senha(sessao, senha)
    if not await redis.exists(chave_sms_pend_hash(id_externo)):
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    await _repo_sms_pend.remover(redis, id_externo)


async def patch_redis_sms_esperando(redis: Redis, message_id: str, body: dict[str, Any]) -> dict[str, Any]:
    mapping = _montar_patch_redis_hash(body, permitidas=_WHITELIST_SMS_ESP, bloqueadas=_BLOCK_SMS_ESP)
    if not await redis.exists(chave_sms_esp_hash(message_id)):
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    await _repo_sms_esp.atualizar_campos(redis, message_id, mapping)
    return await _linha_sms_esperando_apos_patch(redis, message_id)


async def delete_redis_sms_esperando(
    redis: Redis, message_id: str, sessao: dict[str, Any], senha: str
) -> None:
    _exigir_senha(sessao, senha)
    if not await redis.exists(chave_sms_esp_hash(message_id)):
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    await _repo_sms_esp.remover(redis, message_id)

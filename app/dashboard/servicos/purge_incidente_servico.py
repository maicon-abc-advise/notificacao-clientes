"""Preview e execução do purge de incidente (consultas indevidas)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

import asyncpg
from fastapi import HTTPException
from redis.asyncio import Redis

from app.config.config import obter_configuracao
from app.config.postgres_identificadores import obter_identificadores_postgres
from app.dashboard.servicos.exibicao import (
    enriquecer_linha_postgres,
    enriquecer_redis_email_esperando,
    enriquecer_redis_email_pendente,
    enriquecer_redis_sms_esperando,
    enriquecer_redis_sms_pendente,
)
from app.dashboard.servicos.mutacoes_dashboard_servico import _exigir_senha
from app.dashboard.servicos.serializacao import decodificar_contexto_json_bruto, registo_para_json
from app.orquestracao.repositorios.redis_emails_pendentes_repo import (
    KEY_INDEX as IDX_EMAIL_PEND,
    RepositorioEmailsPendenteRedis,
    chave_hash as chave_email_pend,
)
from app.purge.catalogo_incidente import carregar_catalogo_incidente
from app.reenvio.repositorios.redis_consulta_notificacao import PREFIXO as PREFIXO_TRAVA
from app.reenvio.repositorios.redis_emails_esperando_confirmacao import (
    KEY_SWEEP as IDX_EMAIL_CONF,
    RepositorioEmailsEsperandoConfirmacaoRedis,
    chave_hash as chave_email_conf,
)
from app.reenvio.repositorios.redis_sms_esperando_confirmacao import (
    KEY_SWEEP as IDX_SMS_CONF,
    RepositorioSmsEsperandoConfirmacaoRedis,
    chave_hash as chave_sms_conf,
)
from app.reenvio.repositorios.redis_sms_pendente import (
    KEY_INDEX as IDX_SMS_PEND,
    RepositorioSmsPendenteRedis,
    chave_hash as chave_sms_pend,
)

_log = logging.getLogger(__name__)

_repo_email_pend = RepositorioEmailsPendenteRedis()
_repo_email_esp = RepositorioEmailsEsperandoConfirmacaoRedis()
_repo_sms_pend = RepositorioSmsPendenteRedis()
_repo_sms_esp = RepositorioSmsEsperandoConfirmacaoRedis()


def _purge_habilitado() -> bool:
    cfg = obter_configuracao()
    if cfg.purge_incidente_enabled:
        return True
    from app.config.ambiente import Ambiente

    return cfg.ambiente == Ambiente.LOCAL


def exigir_purge_habilitado() -> None:
    if not _purge_habilitado():
        raise HTTPException(
            status_code=403,
            detail="Purge desabilitado. Defina PURGE_INCIDENTE_ENABLED=true ou AMBIENTE=local.",
        )


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


def _parse_periodo(s: str) -> datetime:
    t = s.strip()
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    return datetime.fromisoformat(t)


def _secao(
    *,
    secao_id: str,
    titulo: str,
    armazenamento: str,
    descricao_exata: str,
    criterio_inclusao: str,
    criterio_exclusao: str,
    itens: list[dict[str, Any]],
    colunas: list[str],
) -> dict[str, Any]:
    return {
        "id": secao_id,
        "titulo": titulo,
        "armazenamento": armazenamento,
        "descricao_exata": descricao_exata,
        "criterio_inclusao": criterio_inclusao,
        "criterio_exclusao": criterio_exclusao,
        "total": len(itens),
        "colunas": colunas,
        "itens": itens,
    }


async def _listar_emails_pendentes(redis: Redis, cat) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    ids_raw = await redis.zrevrange(IDX_EMAIL_PEND, 0, -1)
    for ext in ids_raw:
        ext_s = ext.decode() if isinstance(ext, bytes) else str(ext)
        raw = await redis.hgetall(chave_email_pend(ext_s))
        if not raw:
            continue
        cid = (_redis_h(raw, "consulta_id") or "").strip().lower()
        if not cat.consulta_permitida(cid):
            continue
        ctx = decodificar_contexto_json_bruto(_redis_h(raw, "contexto_json"))
        linha: dict[str, Any] = {
            "motivo_inclusao": "consulta_id na lista do incidente",
            "chave_redis": chave_email_pend(ext_s),
            "id_externo": _redis_h(raw, "id_externo") or ext_s,
            "destinatario": _redis_h(raw, "destinatario"),
            "tipo_template": _redis_h(raw, "tipo_template"),
            "cnpj_basico": _redis_h(raw, "cnpj_basico"),
            "consulta_id": cid,
            "origem": _redis_h(raw, "origem"),
            "criado_em": _redis_h(raw, "criado_em"),
            "contexto": ctx if isinstance(ctx, dict) else {},
        }
        out.append(enriquecer_redis_email_pendente(linha))
    return out


async def _listar_sms_pendentes(redis: Redis, cat) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    ids_raw = await redis.zrevrange(IDX_SMS_PEND, 0, -1)
    for ext in ids_raw:
        ext_s = ext.decode() if isinstance(ext, bytes) else str(ext)
        raw = await redis.hgetall(chave_sms_pend(ext_s))
        if not raw:
            continue
        cid = (_redis_h(raw, "consulta_id") or "").strip().lower()
        if not cat.consulta_permitida(cid):
            continue
        ctx = decodificar_contexto_json_bruto(_redis_h(raw, "contexto_json"))
        linha = {
            "motivo_inclusao": "consulta_id na lista do incidente",
            "chave_redis": chave_sms_pend(ext_s),
            "id_externo": _redis_h(raw, "id_externo") or ext_s,
            "telefone": _redis_h(raw, "telefone"),
            "tipo_template": _redis_h(raw, "tipo_template"),
            "cnpj_basico": _redis_h(raw, "cnpj_basico"),
            "consulta_id": cid,
            "origem": _redis_h(raw, "origem"),
            "criado_em": _redis_h(raw, "criado_em"),
            "contexto": ctx if isinstance(ctx, dict) else {},
        }
        out.append(enriquecer_redis_sms_pendente(linha))
    return out


async def _listar_emails_esperando(redis: Redis, cat) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    ids_raw = await redis.zrevrange(IDX_EMAIL_CONF, 0, -1)
    for mid in ids_raw:
        mid_s = mid.decode() if isinstance(mid, bytes) else str(mid)
        raw = await redis.hgetall(chave_email_conf(mid_s))
        if not raw:
            continue
        cid = (_redis_h(raw, "consulta_id") or "").strip().lower()
        if not cat.consulta_permitida(cid):
            continue
        ctx = decodificar_contexto_json_bruto(_redis_h(raw, "contexto_json"))
        linha = {
            "motivo_inclusao": "consulta_id na lista do incidente",
            "chave_redis": chave_email_conf(mid_s),
            "message_id_zenvia": mid_s,
            "id_externo": _redis_h(raw, "id_externo"),
            "email_destinatario": _redis_h(raw, "email_destinatario"),
            "tipo_template": _redis_h(raw, "tipo_template"),
            "cnpj_basico": _redis_h(raw, "cnpj_basico"),
            "consulta_id": cid,
            "status_atual": _redis_h(raw, "status_atual"),
            "criado_em": _redis_h(raw, "criado_em"),
            "contexto": ctx if isinstance(ctx, dict) else {},
        }
        out.append(enriquecer_redis_email_esperando(linha))
    return out


async def _listar_sms_esperando(redis: Redis, cat) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    ids_raw = await redis.zrevrange(IDX_SMS_CONF, 0, -1)
    for mid in ids_raw:
        mid_s = mid.decode() if isinstance(mid, bytes) else str(mid)
        raw = await redis.hgetall(chave_sms_conf(mid_s))
        if not raw:
            continue
        cid = (_redis_h(raw, "consulta_id") or "").strip().lower()
        if not cat.consulta_permitida(cid):
            continue
        ctx = decodificar_contexto_json_bruto(_redis_h(raw, "contexto_json"))
        linha = {
            "motivo_inclusao": "consulta_id na lista do incidente",
            "chave_redis": chave_sms_conf(mid_s),
            "message_id_zenvia": mid_s,
            "id_externo": _redis_h(raw, "id_externo"),
            "telefone_destinatario": _redis_h(raw, "telefone_destinatario"),
            "tipo_template": _redis_h(raw, "tipo_template"),
            "cnpj_basico": _redis_h(raw, "cnpj_basico"),
            "consulta_id": cid,
            "status_atual": _redis_h(raw, "status_atual"),
            "criado_em": _redis_h(raw, "criado_em"),
            "contexto": ctx if isinstance(ctx, dict) else {},
        }
        out.append(enriquecer_redis_sms_esperando(linha))
    return out


async def _listar_travas(redis: Redis, cat) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for par in cat.pares_consulta_cnpj:
        cid = par["consulta_id"]
        cnpj = par["cnpj_basico"]
        chave = f"{PREFIXO_TRAVA}:{cid}:{cnpj}"
        val = await redis.get(chave)
        if not val:
            continue
        fase = val.decode() if isinstance(val, bytes) else str(val)
        out.append(
            {
                "motivo_inclusao": "par (consulta_id, cnpj_basico) do incidente com trava existente",
                "chave_redis": chave,
                "consulta_id": cid,
                "cnpj_basico": cnpj,
                "fase_atual": fase,
            }
        )
    return out


def _id_externos_redis(secoes_redis: list[list[dict[str, Any]]]) -> set[str]:
    ids: set[str] = set()
    for itens in secoes_redis:
        for row in itens:
            ext = str(row.get("id_externo") or "").strip()
            if ext:
                ids.add(ext)
    return ids


async def _listar_postgres_enviados(
    pool: asyncpg.Pool,
    *,
    tabela_logica: str,
    canal: str,
    cat,
    id_externos_redis: set[str],
) -> list[dict[str, Any]]:
    p = obter_identificadores_postgres()
    tabela = p.qual(tabela_logica)
    inicio = _parse_periodo(cat.periodo_inicio)
    fim = _parse_periodo(cat.periodo_fim)
    cnpjs = list(cat.cnpjs_basicos)
    ids_redis = list(id_externos_redis)

    rows = await pool.fetch(
        f"""
        SELECT *
        FROM {tabela}
        WHERE (
            (cardinality($1::text[]) > 0 AND id_externo = ANY($1::text[]))
            OR (
                cardinality($2::text[]) > 0
                AND cnpj_basico = ANY($2::text[])
                AND criado_em >= $3
                AND criado_em < $4
            )
        )
        ORDER BY criado_em DESC NULLS LAST, id DESC
        """,
        ids_redis,
        cnpjs,
        inicio,
        fim,
    )

    out: list[dict[str, Any]] = []
    vistos: set[str] = set()
    for r in rows:
        item = registo_para_json(r)
        pk = str(item.get("id") or item.get("id_externo") or "")
        if pk in vistos:
            continue
        vistos.add(pk)
        ext = str(item.get("id_externo") or "").strip()
        cnpj = str(item.get("cnpj_basico") or "").strip()
        if ext and ext in id_externos_redis:
            motivo = "id_externo também presente nas filas Redis do preview"
        elif cnpj in cat.cnpjs_basicos:
            motivo = (
                f"cnpj_basico do incidente + criado_em entre {cat.periodo_inicio} e {cat.periodo_fim}"
            )
        else:
            continue
        item["motivo_inclusao"] = motivo
        item["consulta_id"] = None
        out.append(enriquecer_linha_postgres(item, canal=canal))
    return out


async def montar_preview(pool: asyncpg.Pool, redis: Redis) -> dict[str, Any]:
    exigir_purge_habilitado()
    cat = carregar_catalogo_incidente()

    emails_pend = await _listar_emails_pendentes(redis, cat)
    sms_pend = await _listar_sms_pendentes(redis, cat)
    emails_esp = await _listar_emails_esperando(redis, cat)
    sms_esp = await _listar_sms_esperando(redis, cat)
    travas = await _listar_travas(redis, cat)
    ids_redis = _id_externos_redis([emails_pend, sms_pend, emails_esp, sms_esp])
    emails_pg = await _listar_postgres_enviados(
        pool, tabela_logica="emails_enviados", canal="email", cat=cat, id_externos_redis=ids_redis
    )
    sms_pg = await _listar_postgres_enviados(
        pool, tabela_logica="sms_enviados", canal="sms", cat=cat, id_externos_redis=ids_redis
    )

    secoes = [
        _secao(
            secao_id="emails_pendentes",
            titulo="E-mails a enviar (fila Redis)",
            armazenamento="Redis · hash emails-pendentes:{id_externo} + índice emails-pendentes:por_tempo",
            descricao_exata=(
                "Entradas na fila antes do consumidor (n8n) disparar o e-mail. "
                "Cada linha é um hash completo removido com DEL + ZREM."
            ),
            criterio_inclusao=(
                "Campo consulta_id do hash ∈ lista de 29 consultas indevidas (consultas_indevidas.json)."
            ),
            criterio_exclusao=(
                "Itens sem consulta_id, com consulta_id fora da lista, ou filas de outros ambientes."
            ),
            itens=emails_pend,
            colunas=[
                "motivo_inclusao",
                "chave_redis",
                "id_externo",
                "destinatario",
                "consulta_id",
                "cnpj_basico",
                "tipo_template",
                "origem",
                "criado_em",
            ],
        ),
        _secao(
            secao_id="sms_pendentes",
            titulo="SMS a enviar (fila Redis)",
            armazenamento="Redis · hash sms-pendente:{id_externo} + índice sms-pendente:por_tempo",
            descricao_exata="Fila de SMS pendentes de envio; remoção igual à de e-mails pendentes.",
            criterio_inclusao="consulta_id ∈ consultas indevidas.",
            criterio_exclusao="Demais consultas ou registros sem consulta_id.",
            itens=sms_pend,
            colunas=[
                "motivo_inclusao",
                "chave_redis",
                "id_externo",
                "telefone",
                "consulta_id",
                "cnpj_basico",
                "tipo_template",
                "origem",
                "criado_em",
            ],
        ),
        _secao(
            secao_id="emails_esperando_confirmacao",
            titulo="E-mails esperando confirmação (Redis)",
            armazenamento=(
                "Redis · hash emails-esperando-confirmacao:{message_id} + sweep + lookup id_externo"
            ),
            descricao_exata=(
                "E-mails já enviados ao provedor, aguardando webhook/sweep. "
                "Remove hash, sorted set sweep e chave de lookup por id_externo."
            ),
            criterio_inclusao="consulta_id ∈ consultas indevidas.",
            criterio_exclusao="Mensagens de outras consultas.",
            itens=emails_esp,
            colunas=[
                "motivo_inclusao",
                "chave_redis",
                "message_id_zenvia",
                "id_externo",
                "email_destinatario",
                "consulta_id",
                "cnpj_basico",
                "status_atual",
                "criado_em",
            ],
        ),
        _secao(
            secao_id="sms_esperando_confirmacao",
            titulo="SMS esperando confirmação (Redis)",
            armazenamento="Redis · hash sms-esperando-confirmacao:{message_id} + sweep",
            descricao_exata="SMS aguardando eventos Zenvia após envio pela API.",
            criterio_inclusao="consulta_id ∈ consultas indevidas.",
            criterio_exclusao="Outros fluxos.",
            itens=sms_esp,
            colunas=[
                "motivo_inclusao",
                "chave_redis",
                "message_id_zenvia",
                "id_externo",
                "telefone_destinatario",
                "consulta_id",
                "cnpj_basico",
                "status_atual",
                "criado_em",
            ],
        ),
        _secao(
            secao_id="travas_orquestracao",
            titulo="Travas orquestração (Redis)",
            armazenamento="Redis · chave orq:consulta-notificacao:{consulta_uuid}:{cnpj8}",
            descricao_exata=(
                "Trava de idempotência por par consulta+fornecedor. "
                "Só entra se a chave existir para um dos 438 pares do incidente."
            ),
            criterio_inclusao="Par (consulta_id, cnpj_basico) em pares_consulta_cnpj E chave EXISTS no Redis.",
            criterio_exclusao="Pares sem trava ativa (nada a apagar).",
            itens=travas,
            colunas=["motivo_inclusao", "chave_redis", "consulta_id", "cnpj_basico", "fase_atual"],
        ),
        _secao(
            secao_id="emails_enviados",
            titulo="Registros Postgres · emails_enviados",
            armazenamento="Postgres · tabela emails_enviados (histórico de envio)",
            descricao_exata="Linhas de histórico deste serviço. DELETE por id (PK uuid).",
            criterio_inclusao=(
                "id_externo listado nas filas Redis acima OU "
                "(cnpj_basico ∈ CNPJs do incidente E criado_em no período do JSON)."
            ),
            criterio_exclusao=(
                "engajamento_fornecedores, consultas, company_profile, usuario_fornecedor. "
                "E-mails fora do período/CNPJ/id_externo."
            ),
            itens=emails_pg,
            colunas=[
                "motivo_inclusao",
                "id",
                "id_externo",
                "cnpj_basico",
                "email_destinatario",
                "tipo_template",
                "status_ultimo",
                "criado_em",
            ],
        ),
        _secao(
            secao_id="sms_enviados",
            titulo="Registros Postgres · sms_enviados",
            armazenamento="Postgres · tabela sms_enviados",
            descricao_exata="Histórico SMS; DELETE por id (PK uuid).",
            criterio_inclusao="Mesma regra de emails_enviados.",
            criterio_exclusao="Mesmas exclusões; sem engajamento.",
            itens=sms_pg,
            colunas=[
                "motivo_inclusao",
                "id",
                "id_externo",
                "cnpj_basico",
                "telefone",
                "tipo_template",
                "status_ultimo",
                "criado_em",
            ],
        ),
    ]

    total = sum(s["total"] for s in secoes)
    return {
        "habilitado": True,
        "catalogo": {
            "descricao": cat.descricao,
            "periodo_inicio": cat.periodo_inicio,
            "periodo_fim": cat.periodo_fim,
            "total_consultas": len(cat.consulta_ids),
            "total_pares_consulta_cnpj": len(cat.pares_consulta_cnpj),
            "total_cnpjs_distintos": len(cat.cnpjs_basicos),
            "consulta_ids": sorted(cat.consulta_ids),
        },
        "nao_sera_apagado": [
            "Tabela consultas (produto principal)",
            "Tabela company_profile",
            "Tabela usuario_fornecedor / auth.users",
            "Tabela engajamento_fornecedores (contadores e contatos permanecem)",
            "Mensagens já entregues na Zenvia (fora deste banco)",
            "webhook_eventos_processados",
        ],
        "total_itens": total,
        "secoes": secoes,
    }


async def executar_purge(
    pool: asyncpg.Pool,
    redis: Redis,
    *,
    sessao: dict[str, Any],
    senha: str,
) -> dict[str, Any]:
    exigir_purge_habilitado()
    _exigir_senha(sessao, senha)
    preview = await montar_preview(pool, redis)
    removidos: dict[str, int] = {}

    for item in preview["secoes"][0]["itens"]:
        ext = str(item.get("id_externo") or "")
        if ext:
            await _repo_email_pend.remover(redis, ext)
    removidos["emails_pendentes"] = preview["secoes"][0]["total"]

    for item in preview["secoes"][1]["itens"]:
        ext = str(item.get("id_externo") or "")
        if ext:
            await _repo_sms_pend.remover(redis, ext)
    removidos["sms_pendentes"] = preview["secoes"][1]["total"]

    for item in preview["secoes"][2]["itens"]:
        mid = str(item.get("message_id_zenvia") or "")
        if mid:
            await _repo_email_esp.remover(redis, mid)
    removidos["emails_esperando_confirmacao"] = preview["secoes"][2]["total"]

    for item in preview["secoes"][3]["itens"]:
        mid = str(item.get("message_id_zenvia") or "")
        if mid:
            await _repo_sms_esp.remover(redis, mid)
    removidos["sms_esperando_confirmacao"] = preview["secoes"][3]["total"]

    n_travas = 0
    for item in preview["secoes"][4]["itens"]:
        chave = str(item.get("chave_redis") or "")
        if chave:
            await redis.delete(chave)
            n_travas += 1
    removidos["travas_orquestracao"] = n_travas

    p = obter_identificadores_postgres()
    for secao_id, tabela in (("emails_enviados", "emails_enviados"), ("sms_enviados", "sms_enviados")):
        sec = next(s for s in preview["secoes"] if s["id"] == secao_id)
        tabela_ql = p.qual(tabela)
        n = 0
        for item in sec["itens"]:
            pk = item.get("id")
            if not pk:
                continue
            try:
                rid = uuid.UUID(str(pk))
            except ValueError:
                continue
            row = await pool.fetchrow(
                f"DELETE FROM {tabela_ql} WHERE id = $1 RETURNING id",
                rid,
            )
            if row:
                n += 1
        removidos[secao_id] = n

    _log.warning("Purge de incidente executado: %s", removidos)
    return {"ok": True, "removidos": removidos, "total": sum(removidos.values())}

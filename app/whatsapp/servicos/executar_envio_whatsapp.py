"""Envio manual/automático de mensagem WhatsApp + validação de número."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg

from app.config.config import Configuracao
from app.config.postgres_identificadores import obter_identificadores_postgres
from app.ligacoes.servicos.entrada_ligacao_apos_falha_whatsapp import convidar_ligacao_apos_falha_whatsapp
from app.orquestracao.repositorios.engajamento_consulta_repo import carregar_por_cnpj_basico
from app.orquestracao.repositorios.company_profile_repo import buscar_full_profile_por_cnpj_basico
from app.whatsapp.api.externo.evolution.adaptador_evolution import (
    ErroEvolutionAPI,
    aplicar_label_chat,
    enviar_texto,
    resolver_label_id,
    verificar_numero_whatsapp,
)
from app.whatsapp.repositorios import postgres_whatsapp_envios as repo
from app.whatsapp.repositorios.postgres_whatsapp_envios import cnpj_de_row
from app.whatsapp.repositorios.redis_contato_fornecedores import enfileirar_contato_fornecedor
from app.whatsapp.repositorios.redis_historico_whatsapp import append_mensagem_agente_historico_redis
from app.whatsapp.servicos.mensagem_inicial import escolher_mensagem_contato
from app.whatsapp.servicos.tocar_engajamento_whatsapp import tocar_engajamento_whatsapp, WhatsappEngajamentoEstado

_log = logging.getLogger(__name__)


async def _resolver_segmento(pool: asyncpg.Pool, cnpj_basico: str) -> str | None:
    profile, _uf = await buscar_full_profile_por_cnpj_basico(pool, cnpj_basico=cnpj_basico)
    if profile:
        ind = profile.get("industria") or profile.get("segmento")
        if ind:
            return str(ind).strip()
    snap = await carregar_por_cnpj_basico(pool, cnpj_basico)
    ctx = getattr(snap, "contexto_ultima_consulta", None) or {}
    for chave in ("v_produto", "v_servico", "segmento"):
        val = ctx.get(chave) if isinstance(ctx, dict) else None
        if val:
            return str(val).strip()
    return None


async def _cache_whatsapp_invalido(pool: asyncpg.Pool, cnpj_basico: str, telefone: str, cfg: Configuracao) -> bool:
    """Se company_profile marcou inválido recentemente, pula Evolution."""
    p = obter_identificadores_postgres()
    try:
        row = await pool.fetchrow(
            f"""
            SELECT whatsapp_valido, whatsapp_validado_em
            FROM {p.qual('company_profile')} cp
            WHERE cp.cnpj LIKE $1 || '%'
            LIMIT 1
            """,
            cnpj_basico.strip()[:8],
        )
    except asyncpg.UndefinedTableError:
        return False
    if not row or row["whatsapp_valido"] is not False:
        return False
    val_em = row["whatsapp_validado_em"]
    if not val_em:
        return True
    if isinstance(val_em, datetime) and val_em.tzinfo is None:
        val_em = val_em.replace(tzinfo=UTC)
    limite = datetime.now(UTC) - timedelta(days=cfg.whatsapp_validacao_cache_dias)
    return val_em >= limite


async def validar_e_atualizar_numero(
    pool: asyncpg.Pool,
    cfg: Configuracao,
    envio_id: uuid.UUID | str,
) -> dict[str, Any]:
    row = await repo.buscar_por_id(pool, envio_id)
    if not row:
        raise ValueError("Envio WhatsApp não encontrado")
    tel = str(row["numero_telefone"])
    cnpj = cnpj_de_row(row)

    if await _cache_whatsapp_invalido(pool, cnpj, tel, cfg):
        exists = False
    else:
        try:
            exists = await verificar_numero_whatsapp(cfg, tel)
        except ErroEvolutionAPI as exc:
            return {"acao": "whatsapp_erro_api_retry", "id": str(row["id"]), "erro": str(exc)}

    wa_status = "valido" if exists else "invalido"
    await repo.atualizar_status(pool, row["id"], whatsapp_status=wa_status)
    estado = WhatsappEngajamentoEstado.WHATSAPP_VALIDO if exists else WhatsappEngajamentoEstado.WHATSAPP_INVALIDO
    await tocar_engajamento_whatsapp(
        pool, row.get("fornecedor_id"), cnpj, estado, telefone=tel
    )
    return {
        "acao": "validar_numero",
        "id": str(row["id"]),
        "whatsapp_status": wa_status,
        "exists": exists,
    }


async def _finalizar_whatsapp_numero_invalido(
    pool: asyncpg.Pool,
    row: asyncpg.Record,
) -> dict[str, Any]:
    """Número sem WhatsApp: encerra funil (1 linha por CNPJ) e convida ligação."""
    cnpj = cnpj_de_row(row)
    tel_atual = str(row["numero_telefone"])
    atualizado = await repo.atualizar_status(
        pool,
        row["id"],
        status="concluido_falha",
        whatsapp_status="invalido",
        motivo_falha="sem_whatsapp_valido",
    )
    await tocar_engajamento_whatsapp(
        pool,
        row.get("fornecedor_id"),
        cnpj,
        WhatsappEngajamentoEstado.WHATSAPP_CONCLUIDO_FALHA,
        telefone=tel_atual,
    )
    ligacao = await convidar_ligacao_apos_falha_whatsapp(
        pool,
        atualizado or row,
        origem="whatsapp_sem_numero_valido",
    )
    return {
        "acao": "whatsapp_sem_whatsapp_valido",
        "id": str(row["id"]),
        "ligacao": ligacao,
    }


async def enviar_mensagem_inicial(
    pool: asyncpg.Pool,
    cfg: Configuracao,
    envio_id: uuid.UUID | str,
    *,
    mensagem: str | None = None,
) -> dict[str, Any]:
    row = await repo.buscar_por_id(pool, envio_id)
    if not row:
        raise ValueError("Envio WhatsApp não encontrado")

    status_antes = str(row["status"])
    tel = str(row["numero_telefone"])
    cnpj = cnpj_de_row(row)

    validacao = await validar_e_atualizar_numero(pool, cfg, row["id"])
    if validacao.get("acao") == "whatsapp_erro_api_retry":
        return validacao
    if not validacao.get("exists"):
        return await _finalizar_whatsapp_numero_invalido(pool, row)

    segmento = await _resolver_segmento(pool, cnpj)
    texto = (mensagem or "").strip() or escolher_mensagem_contato(row, segmento)

    try:
        await enviar_texto(cfg, tel, texto)
        label_id = await resolver_label_id(cfg)
        if label_id:
            try:
                await aplicar_label_chat(cfg, tel, label_id)
            except ErroEvolutionAPI as exc:
                _log.warning("Etiqueta não aplicada: %s", exc)
    except ErroEvolutionAPI as exc:
        return {
            "acao": "whatsapp_erro_api_retry",
            "id": str(row["id"]),
            "status_antes": status_antes,
            "erro": str(exc),
        }

    redis_historico_key: str | None = None
    try:
        redis_historico_key = await append_mensagem_agente_historico_redis(tel, texto)
    except Exception as exc:
        _log.warning("Histórico Redis não gravado (envio WhatsApp ok): %s", exc)

    atualizado = await repo.atualizar_status(
        pool, row["id"], status="contatado", whatsapp_status="valido"
    )
    await tocar_engajamento_whatsapp(
        pool,
        row.get("fornecedor_id"),
        cnpj,
        WhatsappEngajamentoEstado.WHATSAPP_CONTATADO,
        telefone=tel,
    )

    redis_telefones: list[str] | None = None
    redis_enqueued = False
    try:
        redis_telefones = await enfileirar_contato_fornecedor(cfg, tel)
        redis_enqueued = redis_telefones is not None
    except Exception as exc:
        _log.warning("Fila contato-fornecedores não enfileirada (envio WhatsApp ok): %s", exc)

    return {
        "acao": "enviar_mensagem",
        "id": str(row["id"]),
        "status_antes": status_antes,
        "status_depois": "contatado",
        "mensagem_enviada": True,
        "redis_enqueued": redis_enqueued,
        "redis_telefones": redis_telefones,
        "redis_historico_key": redis_historico_key,
        "numero_telefone": tel,
        "registro": dict(atualizado) if atualizado else None,
    }

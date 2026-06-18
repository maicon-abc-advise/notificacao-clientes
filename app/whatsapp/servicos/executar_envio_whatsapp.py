"""Envio manual/automático de mensagem WhatsApp + validação de número."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg

from app.config.config import Configuracao
from app.config.postgres_identificadores import obter_identificadores_postgres
from app.orquestracao.repositorios.engajamento_consulta_repo import carregar_por_cnpj_basico
from app.orquestracao.repositorios.company_profile_repo import buscar_full_profile_por_cnpj_basico
from app.reenvio.servicos.engajamento_contatos import proximo_telefone_tentavel_apos_contato
from app.whatsapp.api.externo.evolution.adaptador_evolution import (
    ErroEvolutionAPI,
    aplicar_label_chat,
    enviar_texto,
    resolver_label_id,
    verificar_numero_whatsapp,
)
from app.whatsapp.repositorios import postgres_whatsapp_envios as repo
from app.whatsapp.servicos.entrada_whatsapp_apos_falha_email import entrada_whatsapp_apos_falha_email
from app.whatsapp.servicos.mensagem_inicial import montar_mensagem_inicial
from app.whatsapp.servicos.telefone_whatsapp import normalizar_telefone_whatsapp
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
    cnpj = str(row["cnpj_basico"])

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


async def _tentar_proximo_telefone(
    pool: asyncpg.Pool,
    cfg: Configuracao,
    row: asyncpg.Record,
) -> dict[str, Any] | None:
    cnpj = str(row["cnpj_basico"])
    tel_atual = str(row["numero_telefone"])
    snap = await carregar_por_cnpj_basico(pool, cnpj)
    prox = proximo_telefone_tentavel_apos_contato(snap.contatos_sms, tel_atual)
    if not prox:
        await repo.atualizar_status(
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
        return {"acao": "whatsapp_sem_whatsapp_valido", "id": str(row["id"])}

    entrada = await entrada_whatsapp_apos_falha_email(
        pool,
        cfg,
        cnpj_basico=cnpj,
        fornecedor_id=row.get("fornecedor_id"),
        origem="proximo_telefone_invalido",
        telefone=prox,
    )
    return {"acao": "whatsapp_numero_invalido_proximo", "id": str(row["id"]), **entrada}


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
    cnpj = str(row["cnpj_basico"])

    validacao = await validar_e_atualizar_numero(pool, cfg, row["id"])
    if validacao.get("acao") == "whatsapp_erro_api_retry":
        return validacao
    if not validacao.get("exists"):
        prox = await _tentar_proximo_telefone(pool, cfg, row)
        return prox or validacao

    texto = (mensagem or "").strip() or montar_mensagem_inicial(await _resolver_segmento(pool, cnpj))

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
    return {
        "acao": "enviar_mensagem",
        "id": str(row["id"]),
        "status_antes": status_antes,
        "status_depois": "contatado",
        "mensagem_enviada": True,
        "numero_telefone": tel,
        "registro": dict(atualizado) if atualizado else None,
    }

"""Sweep da fila ``sms-esperando-confirmacao``: reenfileira SMS com novo ``id_externo`` (engajamento)."""

from __future__ import annotations

import json
import logging
import time
import uuid

import asyncpg
from redis.asyncio import Redis

from app.config.config import Configuracao
from app.orquestracao.repositorios.engajamento_consulta_repo import carregar_por_cnpj_basico
from app.reenvio.repositorios.redis_consulta_notificacao import parse_consulta_id_hash
from app.reenvio.repositorios.redis_sms_esperando_confirmacao import (
    KEY_SWEEP,
    RepositorioSmsEsperandoConfirmacaoRedis,
)
from app.reenvio.repositorios.redis_sms_pendente import RepositorioSmsPendenteRedis
from app.reenvio.servicos.engajamento_contatos import (
    agregado_canal_bloqueado,
    escolher_telefone_efetivo,
    proximo_telefone_tentavel_apos_contato,
)
from app.reenvio.servicos.engajamento_estado import EngajamentoSmsEstado
from app.reenvio.servicos.engajamento_fornecedor import parse_fornecedor_id, tocar_engajamento_sms

_log = logging.getLogger(__name__)


def _contexto_de_hash(campos: dict[str, str]) -> dict[str, str]:
    try:
        base = json.loads(campos.get("contexto_json") or "{}")
    except json.JSONDecodeError:
        base = {}
    if not isinstance(base, dict):
        base = {}
    return {str(k): str(v) for k, v in base.items() if v is not None}


async def executar_sweep_sms_esperando_confirmacao(
    pool: asyncpg.Pool,
    redis: Redis,
    cfg: Configuracao,
) -> dict[str, int]:
    repo_esp = RepositorioSmsEsperandoConfirmacaoRedis()
    repo_s = RepositorioSmsPendenteRedis()
    agora = int(time.time())
    ids = await repo_esp.listar_sweep_elegiveis(redis, ate_ts=agora)
    inseridos = 0
    ignorados = 0

    for message_id in ids:
        campos = await repo_esp.obter(redis, message_id)
        if not campos:
            await redis.zrem(KEY_SWEEP, message_id)
            ignorados += 1
            continue

        ext = (campos.get("id_externo") or campos.get("external_id") or "").strip()
        tel_cur = (campos.get("telefone_destinatario") or "").strip() or None
        cnpj_basico = (campos.get("cnpj_basico") or "").strip() or None
        status_atual = (campos.get("status_atual") or "").strip().upper()

        # Legado: DELIVERED só atualizava o hash; limpa sem novo envio.
        if status_atual == "ENTREGUE":
            await repo_esp.remover(redis, message_id)
            ignorados += 1
            continue

        destino: str | None = None
        if cnpj_basico:
            snap = await carregar_por_cnpj_basico(pool, cnpj_basico)
            if agregado_canal_bloqueado(snap.engajamento_sms):
                ignorados += 1
                novo_sweep = agora + cfg.sweep_emails_esperando_confirmacao_dias * 86400
                await repo_esp.reagendar_sweep(redis, message_id, novo_sweep)
                continue
            destino = proximo_telefone_tentavel_apos_contato(snap.contatos_sms, tel_cur)
            if not destino:
                destino = escolher_telefone_efetivo(snap.contatos_sms, None)

        destino = (destino or "").strip()
        if not destino:
            _log.warning(
                "Sweep SMS: sem telefone tentável; reagendado. message_id=%s id_externo=%s",
                message_id,
                ext,
            )
            ignorados += 1
            novo_sweep = agora + cfg.sweep_emails_esperando_confirmacao_dias * 86400
            await repo_esp.reagendar_sweep(redis, message_id, novo_sweep)
            continue

        ctx = _contexto_de_hash(campos)
        uid_s = (campos.get("fornecedor_id") or campos.get("usuario_id") or "").strip() or None
        cid = parse_consulta_id_hash(campos.get("consulta_id"))
        sms_ext = f"{ext}:sms_sweep:{uuid.uuid4().hex[:16]}"
        ok = await repo_s.criar(
            redis,
            id_externo=sms_ext,
            telefone=destino,
            tipo_template=(campos.get("tipo_template") or "").strip(),
            contexto=ctx,
            remetente=(campos.get("remetente") or None) or None,
            origem="sweep_sms_esperando_confirmacao",
            fornecedor_id=uid_s if uid_s else None,
            cnpj_basico=cnpj_basico,
            consulta_id=cid,
            sobrescrever_trava_de_sms_esperando=True,
        )
        if ok:
            inseridos += 1
            await tocar_engajamento_sms(
                pool,
                parse_fornecedor_id(uid_s),
                cnpj_basico,
                EngajamentoSmsEstado.SMS_REPROCESSAR_FILA,
                endereco=destino,
            )
            await repo_esp.remover(redis, message_id)
        else:
            ignorados += 1
            novo_sweep = agora + cfg.sweep_emails_esperando_confirmacao_dias * 86400
            await repo_esp.reagendar_sweep(redis, message_id, novo_sweep)

    return {"inseridos": inseridos, "ignorados": ignorados, "candidatos": len(ids)}

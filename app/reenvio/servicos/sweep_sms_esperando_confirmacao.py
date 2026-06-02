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


async def _encerrar_sms_esperando_sem_canal(
    pool: asyncpg.Pool,
    redis: Redis,
    repo_esp: RepositorioSmsEsperandoConfirmacaoRedis,
    *,
    message_id: str,
    cnpj_basico: str | None,
    telefone_destinatario: str | None,
    fornecedor_id: uuid.UUID | None,
    id_externo: str,
    motivo_log: str,
) -> None:
    if cnpj_basico and telefone_destinatario:
        await tocar_engajamento_sms(
            pool,
            fornecedor_id,
            cnpj_basico,
            EngajamentoSmsEstado.SMS_SWEEP_SEM_CANAL,
            endereco=telefone_destinatario,
        )
    _log.info(
        "Sweep SMS: %s; removido de esperando confirmação. message_id=%s id_externo=%s cnpj_basico=%s",
        motivo_log,
        message_id,
        id_externo,
        cnpj_basico or "",
    )
    await repo_esp.remover(redis, message_id)


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
        uid_s = (campos.get("fornecedor_id") or campos.get("usuario_id") or "").strip() or None
        fid = parse_fornecedor_id(uid_s)
        status_atual = (campos.get("status_atual") or "").strip().upper()

        # Legado: DELIVERED só atualizava o hash; limpa sem novo envio.
        if status_atual == "ENTREGUE":
            await repo_esp.remover(redis, message_id)
            ignorados += 1
            continue

        destino: str | None = None
        if cnpj_basico:
            snap = await carregar_por_cnpj_basico(pool, cnpj_basico)
            destino = proximo_telefone_tentavel_apos_contato(snap.contatos_sms, tel_cur)
            if not destino:
                destino = escolher_telefone_efetivo(snap.contatos_sms, None)

        destino = (destino or "").strip()
        if not destino:
            await _encerrar_sms_esperando_sem_canal(
                pool,
                redis,
                repo_esp,
                message_id=message_id,
                cnpj_basico=cnpj_basico,
                telefone_destinatario=tel_cur,
                fornecedor_id=fid,
                id_externo=ext,
                motivo_log="sem próximo telefone tentável no engajamento",
            )
            ignorados += 1
            continue

        ctx = _contexto_de_hash(campos)
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
                fid,
                cnpj_basico,
                EngajamentoSmsEstado.SMS_REPROCESSAR_FILA,
                endereco=destino,
            )
            await repo_esp.remover(redis, message_id)
        else:
            await _encerrar_sms_esperando_sem_canal(
                pool,
                redis,
                repo_esp,
                message_id=message_id,
                cnpj_basico=cnpj_basico,
                telefone_destinatario=tel_cur,
                fornecedor_id=fid,
                id_externo=ext,
                motivo_log="SMS pendente não aceito (sem outro canal útil)",
            )
            ignorados += 1

    return {"inseridos": inseridos, "ignorados": ignorados, "candidatos": len(ids)}

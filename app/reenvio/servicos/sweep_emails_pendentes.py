from __future__ import annotations
import logging
import time
import uuid
import asyncpg
from redis.asyncio import Redis
from app.config.config import Configuracao
from app.reenvio.repositorios.redis_email_pendente import KEY_SWEEP, RepositorioEmailPendenteRedis
from app.reenvio.repositorios.redis_sms_pendente import RepositorioSmsPendenteRedis
from app.reenvio.servicos.engajamento_estado import EngajamentoEstado
from app.reenvio.servicos.engajamento_usuario import parse_usuario_id, tocar_engajamento
from app.reenvio.servicos.processar_status_email import TEMPLATE_SMS_EMAIL_INVALIDO, _contexto_sms_de_hash

_log = logging.getLogger(__name__)


async def executar_sweep_emails_pendentes(
    pool: asyncpg.Pool,
    redis: Redis,
    cfg: Configuracao,
) -> dict[str, int]:
    repo_e = RepositorioEmailPendenteRedis()
    repo_s = RepositorioSmsPendenteRedis()
    agora = int(time.time())
    ids = await repo_e.listar_sweep_elegiveis(redis, ate_ts=agora)
    inseridos = 0
    ignorados = 0
    for message_id in ids:
        campos = await repo_e.obter(redis, message_id)
        if not campos:
            await redis.zrem(KEY_SWEEP, message_id)
            ignorados += 1
            continue

        tel = (campos.get("telefone_sms_fallback") or "").strip()
        ext = campos.get("external_id") or ""

        if not tel:
            _log.warning(
                "Sweep: pendente sem telefone_sms_fallback; ignorado. message_id=%s external_id=%s",
                message_id,
                ext,
            )
            ignorados += 1
            novo_sweep = agora + cfg.sweep_email_pendente_dias * 86400
            await repo_e.reagendar_sweep(redis, message_id, novo_sweep)
            continue

        sms_ext = f"{ext}:sweep:{uuid.uuid4().hex[:16]}"
        ctx = _contexto_sms_de_hash(campos)
        uid_s = campos.get("usuario_id") or None
        ok = await repo_s.criar(
            redis,
            external_id=sms_ext,
            telefone=tel,
            tipo_template=TEMPLATE_SMS_EMAIL_INVALIDO,
            contexto=ctx,
            remetente=(campos.get("remetente") or None) or None,
            origem="sweep_email_pendente",
            usuario_id=uid_s if uid_s else None,
        )
        if ok:
            inseridos += 1
            await tocar_engajamento(pool, parse_usuario_id(uid_s), EngajamentoEstado.EMAIL_SWEEP_LEMBRETE_SMS)
        else:
            ignorados += 1

        novo_sweep = agora + cfg.sweep_email_pendente_dias * 86400
        await repo_e.reagendar_sweep(redis, message_id, novo_sweep)

    return {"inseridos": inseridos, "ignorados": ignorados, "candidatos": len(ids)}

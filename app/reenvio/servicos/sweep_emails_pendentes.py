from __future__ import annotations
import logging
import time
import uuid
import asyncpg
from redis.asyncio import Redis
from app.config.config import Configuracao
from app.orquestracao.repositorios.engajamento_consulta_repo import carregar_por_cnpj_basico
from app.reenvio.repositorios.redis_emails_esperando_confirmacao import (
    KEY_SWEEP,
    RepositorioEmailsEsperandoConfirmacaoRedis,
)
from app.reenvio.repositorios.redis_consulta_notificacao import parse_consulta_id_hash
from app.reenvio.repositorios.redis_sms_pendente import RepositorioSmsPendenteRedis
from app.reenvio.servicos.engajamento_contatos import escolher_telefone_efetivo
from app.reenvio.servicos.engajamento_estado import EngajamentoEmailEstado
from app.reenvio.servicos.engajamento_fornecedor import parse_fornecedor_id, tocar_engajamento_email
from app.reenvio.servicos.enfileirar_proximo_email_de_esperando import tentar_enfileirar_proximo_email_engajamento
from app.reenvio.servicos.processar_status_email import TEMPLATE_SMS_EMAIL_INVALIDO, _contexto_sms_de_hash

_log = logging.getLogger(__name__)


async def _encerrar_esperando_sem_canal(
    pool: asyncpg.Pool,
    redis: Redis,
    repo_e: RepositorioEmailsEsperandoConfirmacaoRedis,
    *,
    message_id: str,
    cnpj_basico: str | None,
    email_destinatario: str | None,
    fornecedor_id: uuid.UUID | None,
    id_externo: str,
    motivo_log: str,
) -> None:
    if cnpj_basico:
        await tocar_engajamento_email(
            pool,
            fornecedor_id,
            cnpj_basico,
            EngajamentoEmailEstado.EMAIL_SWEEP_SEM_CANAL,
            endereco=email_destinatario,
        )
    _log.info(
        "Sweep: %s; removido de esperando confirmação. message_id=%s id_externo=%s cnpj_basico=%s",
        motivo_log,
        message_id,
        id_externo,
        cnpj_basico or "",
    )
    await repo_e.remover(redis, message_id)


async def executar_sweep_emails_pendentes(
    pool: asyncpg.Pool,
    redis: Redis,
    cfg: Configuracao,
) -> dict[str, int]:
    repo_e = RepositorioEmailsEsperandoConfirmacaoRedis()
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

        ext = (campos.get("id_externo") or campos.get("external_id") or "").strip()
        em_cur = (campos.get("email_destinatario") or "").strip() or None
        cnpj_basico = (campos.get("cnpj_basico") or "").strip() or None
        uid_s = (campos.get("fornecedor_id") or campos.get("usuario_id") or "").strip() or None
        fid = parse_fornecedor_id(uid_s)

        if cnpj_basico:
            snap = await carregar_por_cnpj_basico(pool, cnpj_basico)
            novo_ext = await tentar_enfileirar_proximo_email_engajamento(
                redis,
                campos,
                snap,
                email_atual=em_cur,
                origem="sweep_proximo_email",
                message_id_esperando=message_id,
            )
            if novo_ext:
                inseridos += 1
                await tocar_engajamento_email(
                    pool,
                    fid,
                    cnpj_basico,
                    EngajamentoEmailEstado.EMAIL_SWEEP_PROXIMO_EMAIL,
                    endereco=em_cur,
                )
                continue
            tel = escolher_telefone_efetivo(snap.contatos_sms, None)
        else:
            tel = None

        tel = (tel or "").strip()
        if not tel:
            await _encerrar_esperando_sem_canal(
                pool,
                redis,
                repo_e,
                message_id=message_id,
                cnpj_basico=cnpj_basico,
                email_destinatario=em_cur,
                fornecedor_id=fid,
                id_externo=ext,
                motivo_log="sem próximo e-mail nem telefone no engajamento",
            )
            ignorados += 1
            continue

        sms_ext = f"{ext}:sweep:{uuid.uuid4().hex[:16]}"
        ctx = _contexto_sms_de_hash(
            campos,
            url_plataforma_sms=cfg.url_plataforma_sms,
            url_login_sms=cfg.url_login_sms,
        )
        cid = parse_consulta_id_hash(campos.get("consulta_id"))
        ok = await repo_s.criar(
            redis,
            id_externo=sms_ext,
            telefone=tel,
            tipo_template=TEMPLATE_SMS_EMAIL_INVALIDO,
            contexto=ctx,
            remetente=(campos.get("remetente") or None) or None,
            origem="sweep_emails_esperando_confirmacao",
            fornecedor_id=uid_s if uid_s else None,
            cnpj_basico=cnpj_basico,
            consulta_id=cid,
            sobrescrever_trava_de_email_esperando=True,
        )
        if ok:
            inseridos += 1
            await tocar_engajamento_email(
                pool,
                fid,
                cnpj_basico,
                EngajamentoEmailEstado.EMAIL_SWEEP_LEMBRETE_SMS,
                endereco=em_cur,
            )
            if cnpj_basico:
                from app.whatsapp.servicos.entrada_whatsapp_apos_falha_email import (
                    entrada_whatsapp_apos_falha_email,
                )

                await entrada_whatsapp_apos_falha_email(
                    pool,
                    cfg,
                    cnpj_basico=cnpj_basico,
                    fornecedor_id=fid,
                    origem="sweep_emails_esperando_confirmacao",
                    telefone=tel,
                )
            await repo_e.remover(redis, message_id)
        else:
            await _encerrar_esperando_sem_canal(
                pool,
                redis,
                repo_e,
                message_id=message_id,
                cnpj_basico=cnpj_basico,
                email_destinatario=em_cur,
                fornecedor_id=fid,
                id_externo=ext,
                motivo_log="SMS pendente não aceito (sem outro canal útil)",
            )
            ignorados += 1

    return {"inseridos": inseridos, "ignorados": ignorados, "candidatos": len(ids)}

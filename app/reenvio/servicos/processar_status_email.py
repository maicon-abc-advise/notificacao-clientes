from __future__ import annotations
import json
import logging
import time
import uuid
from typing import Any
import asyncpg
from redis.asyncio import Redis
from app.config.config import Configuracao
from app.reenvio.api.dto.webhook_zenvia import WebhookMessageStatusZenvia
from app.reenvio.repositorios.postgres_webhook_eventos import registrar_evento_se_novo
from app.reenvio.repositorios.redis_emails_esperando_confirmacao import (
    RepositorioEmailsEsperandoConfirmacaoRedis,
)
from app.reenvio.repositorios.redis_consulta_notificacao import parse_consulta_id_hash
from app.reenvio.repositorios.redis_sms_pendente import RepositorioSmsPendenteRedis
from app.reenvio.servicos.classificar_cause_email import (
    ResultadoClassificacaoEmail,
    classificar_falha_email,
)
from app.orquestracao.repositorios.engajamento_consulta_repo import carregar_por_cnpj_basico
from app.reenvio.servicos.engajamento_contatos import escolher_telefone_efetivo
from app.reenvio.servicos.engajamento_estado import EngajamentoEmailEstado, engajamento_falha_recuperavel_email
from app.reenvio.servicos.engajamento_fornecedor import parse_fornecedor_id, tocar_engajamento_email
from app.reenvio.servicos.enfileirar_proximo_email_de_esperando import tentar_enfileirar_proximo_email_engajamento
from app.mensageria.repositorios.postgres_emails_enviados import (
    atualizar_status_por_id_mensagem_zenvia,
)

_log = logging.getLogger(__name__)

TEMPLATE_SMS_EMAIL_INVALIDO = "CONSULTADO_SEM_EMAIL"

def _contexto_sms_de_hash(campos: dict[str, str]) -> dict[str, str]:
    base = json.loads(campos.get("contexto_json") or "{}")
    if not isinstance(base, dict):
        base = {}
    out: dict[str, str] = {str(k): str(v) for k, v in base.items() if v is not None}
    out.setdefault("url_plataforma", "https://plataforma.local")
    return out

async def processar_webhook_status_email(
    pool: asyncpg.Pool,
    redis: Redis,
    cfg: Configuracao,
    payload: WebhookMessageStatusZenvia,
) -> dict[str, Any]:

    if payload.channel != "email":
        return {"acao": "ignorado", "motivo": "canal não é email"}

    novo = await registrar_evento_se_novo(pool, payload.id)
    if not novo:
        return {"acao": "duplicado", "id_evento": payload.id}

    repo = RepositorioEmailsEsperandoConfirmacaoRedis()
    message_id = payload.messageId
    code = payload.messageStatus.code
    cause = payload.messageStatus.cause
    description = payload.messageStatus.description

    dados = await repo.obter(redis, message_id)
    if not dados:
        _log.info(
            "Webhook e-mail sem registo Redis emails-esperando-confirmacao (message_id=%s). Pode ser envio antigo ou teste.",
            message_id,
        )
        return {"acao": "sem_esperando_confirmacao_redis", "message_id": message_id, "code": code}

    fid_raw = (dados.get("fornecedor_id") or dados.get("usuario_id") or "").strip() or None
    fid = parse_fornecedor_id(fid_raw)
    cnpj_basico = (dados.get("cnpj_basico") or "").strip() or None
    em_dest = (dados.get("email_destinatario") or "").strip() or None

    if code == "READ":
        await atualizar_status_por_id_mensagem_zenvia(
            pool,
            id_mensagem_zenvia=message_id,
            status_ultimo="lido",
        )
        await tocar_engajamento_email(
            pool, fid, cnpj_basico, EngajamentoEmailEstado.EMAIL_LIDO, endereco=em_dest
        )
        await repo.remover(redis, message_id)
        return {"acao": "removido_fila", "message_id": message_id, "code": code}

    if code == "CLICK":
        await atualizar_status_por_id_mensagem_zenvia(
            pool,
            id_mensagem_zenvia=message_id,
            status_ultimo="clicado",
        )
        await tocar_engajamento_email(
            pool, fid, cnpj_basico, EngajamentoEmailEstado.EMAIL_LINK_CLICADO, endereco=em_dest
        )
        await repo.remover(redis, message_id)
        return {"acao": "removido_fila", "message_id": message_id, "code": code}

    if code == "SENT":
        await atualizar_status_por_id_mensagem_zenvia(
            pool,
            id_mensagem_zenvia=message_id,
            status_ultimo="processando",
        )
        await tocar_engajamento_email(
            pool, fid, cnpj_basico, EngajamentoEmailEstado.EMAIL_WEBHOOK_SENT, endereco=em_dest
        )
        await repo.atualizar_campos(redis, message_id, {"status_atual": "ENVIADO_PROVEDOR"})
        return {"acao": "atualizado", "message_id": message_id, "code": code}

    if code == "DELIVERED":
        await atualizar_status_por_id_mensagem_zenvia(
            pool,
            id_mensagem_zenvia=message_id,
            status_ultimo="enviado",
        )
        await tocar_engajamento_email(
            pool, fid, cnpj_basico, EngajamentoEmailEstado.EMAIL_ENTREGUE_CAIXA, endereco=em_dest
        )
        await repo.atualizar_campos(redis, message_id, {"status_atual": "ENTREGUE_CAIXA"})
        return {"acao": "atualizado", "message_id": message_id, "code": code}

    if code in ("NOT_DELIVERED", "REJECTED"):
        cls = classificar_falha_email(cause=cause, description=description)
        if cls == ResultadoClassificacaoEmail.HARD_BOUNCE:
            ext = (dados.get("id_externo") or dados.get("external_id") or "").strip()
            if cnpj_basico:
                snap = await carregar_por_cnpj_basico(pool, cnpj_basico)
                novo_ext = await tentar_enfileirar_proximo_email_engajamento(
                    redis,
                    dados,
                    snap,
                    email_atual=em_dest,
                    origem="bounce_email_proximo",
                    message_id_esperando=message_id,
                )
                if novo_ext:
                    await tocar_engajamento_email(
                        pool,
                        fid,
                        cnpj_basico,
                        EngajamentoEmailEstado.EMAIL_NAO_EXISTE,
                        endereco=em_dest,
                    )
                    await atualizar_status_por_id_mensagem_zenvia(
                        pool,
                        id_mensagem_zenvia=message_id,
                        status_ultimo="falha_definitiva",
                    )
                    return {
                        "acao": "bounce_proximo_email",
                        "novo_id_externo": novo_ext,
                        "message_id": message_id,
                    }
                tel = escolher_telefone_efetivo(snap.contatos_sms, None)
            else:
                tel = None
            tel = (tel or "").strip()
            if not tel:
                _log.error(
                    "Hard bounce sem próximo e-mail e sem telefone no engajamento. id_externo=%s",
                    ext,
                )
                await atualizar_status_por_id_mensagem_zenvia(
                    pool,
                    id_mensagem_zenvia=message_id,
                    status_ultimo="falha_definitiva",
                )
                await tocar_engajamento_email(
                    pool,
                    fid,
                    cnpj_basico,
                    EngajamentoEmailEstado.EMAIL_BOUNCE_HARD_SEM_SMS,
                    endereco=em_dest,
                )
                await repo.remover(redis, message_id)
                return {
                    "acao": "bounce_sem_sms",
                    "id_externo": ext,
                    "message_id": message_id,
                }
            await tocar_engajamento_email(
                pool,
                fid,
                cnpj_basico,
                EngajamentoEmailEstado.EMAIL_NAO_EXISTE,
                endereco=em_dest,
            )
            ctx = _contexto_sms_de_hash(dados)
            sms_ext = f"{ext}:bounce_email:{uuid.uuid4().hex[:12]}"
            sms_redis = RepositorioSmsPendenteRedis()
            uid_sms = (dados.get("fornecedor_id") or dados.get("usuario_id") or "").strip() or None
            cid = parse_consulta_id_hash(dados.get("consulta_id"))
            inseriu = await sms_redis.criar(
                redis,
                id_externo=sms_ext,
                telefone=tel,
                tipo_template=TEMPLATE_SMS_EMAIL_INVALIDO,
                contexto=ctx,
                remetente=(dados.get("remetente") or None) or None,
                origem="bounce_email",
                fornecedor_id=uid_sms if uid_sms else None,
                cnpj_basico=cnpj_basico,
                consulta_id=cid,
                sobrescrever_trava_de_email_esperando=True,
            )
            await atualizar_status_por_id_mensagem_zenvia(
                pool,
                id_mensagem_zenvia=message_id,
                status_ultimo="falha_definitiva",
            )
            await tocar_engajamento_email(
                pool,
                fid,
                cnpj_basico,
                EngajamentoEmailEstado.EMAIL_BOUNCE_HARD_SMS_FILA,
                endereco=em_dest,
            )
            await repo.remover(redis, message_id)
            return {
                "acao": "bounce_sms_enfileirado" if inseriu else "bounce_sms_duplicado",
                "id_externo_sms": sms_ext,
                "inseriu": inseriu,
                "message_id": message_id,
            }

        if cnpj_basico:
            snap = await carregar_por_cnpj_basico(pool, cnpj_basico)
            novo_ext = await tentar_enfileirar_proximo_email_engajamento(
                redis,
                dados,
                snap,
                email_atual=em_dest,
                origem="email_falha_recuperavel_proximo",
                message_id_esperando=message_id,
            )
            if novo_ext:
                await atualizar_status_por_id_mensagem_zenvia(
                    pool,
                    id_mensagem_zenvia=message_id,
                    status_ultimo="reprocessar",
                )
                await tocar_engajamento_email(
                    pool, fid, cnpj_basico, engajamento_falha_recuperavel_email(cls), endereco=em_dest
                )
                return {
                    "acao": "recuperavel_proximo_email",
                    "novo_id_externo": novo_ext,
                    "classificacao": cls.value,
                    "message_id": message_id,
                }

        await atualizar_status_por_id_mensagem_zenvia(
            pool,
            id_mensagem_zenvia=message_id,
            status_ultimo="reprocessar",
        )
        await tocar_engajamento_email(
            pool, fid, cnpj_basico, engajamento_falha_recuperavel_email(cls), endereco=em_dest
        )
        await repo.atualizar_campos(
            redis,
            message_id,
            {"status_atual": "AGUARDANDO_REENVIO", "ultimo_cause": (cause or "")[:500]},
        )
        novo_sweep = int(time.time()) + cfg.sweep_emails_esperando_confirmacao_dias * 86400
        await repo.reagendar_sweep(redis, message_id, novo_sweep)
        return {
            "acao": "reagendado_fila",
            "classificacao": cls.value,
            "message_id": message_id,
        }

    _log.warning("Código de status e-mail não tratado: %s", code)
    return {"acao": "nao_tratado", "code": code, "message_id": message_id}

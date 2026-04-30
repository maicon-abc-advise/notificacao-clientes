from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

import asyncpg
from redis.asyncio import Redis

from app.config.config import Configuracao
from app.orquestracao.api.dto.verificar_creditos_dto import RespostaVerificarCreditos
from app.orquestracao.repositorios.engajamento_consulta_repo import (
    carregar_para_fornecedor,
    registrar_lembrete_creditos_semanal,
)
from app.orquestracao.repositorios.fornecedores_repo import listar_fornecedores_alerta_creditos
from app.orquestracao.servicos.auxiliares.decidir_canal_e_cadencia import (
    email_usavel_para_notificacao,
    telefone_usavel_para_sms,
)
from app.orquestracao.servicos.auxiliares.enfileirar_ou_enviar_interno import (
    enfileirar_email_pendente,
    enfileirar_sms_pendente,
)
from app.orquestracao.servicos.auxiliares.montar_pedido_mensagem import (
    montar_pedido_email_creditos_esgotados,
    montar_pedido_email_creditos_no_fim,
    montar_pedido_sms_creditos_esgotados,
    montar_pedido_sms_creditos_no_fim,
)
from app.templates.modelo import CodigoTipoTemplate

_log = logging.getLogger(__name__)
_ORIGEM = "orquestracao-verificar-creditos"


async def executar_verificar_creditos(
    pool: asyncpg.Pool,
    redis: Redis,
    config: Configuracao,
) -> RespostaVerificarCreditos:
    limiar = config.limiar_creditos_no_fim
    link_creditos = config.link_area_creditos
    rows = await listar_fornecedores_alerta_creditos(pool, limiar=limiar)
    enfileirados = 0
    ignorados = 0

    _log.info(
        "[orquestracao] verificar-creditos inicio limiar=%s fornecedores=%s",
        limiar,
        len(rows),
    )

    for row in rows:
        fid: uuid.UUID = row["fornecedor_id"]
        creditos_restantes: int = row["creditos"]
        email = (row["email"] or "").strip()
        telefone = (row["telefone"] or "").strip()
        nome = row["nome"]

        snap = await carregar_para_fornecedor(pool, fid)

        email_ok = email_usavel_para_notificacao(
            email, recebe_email=snap.recebe_email, engajamento_email=snap.engajamento_email
        )
        sms_ok = telefone_usavel_para_sms(telefone, snap.engajamento_sms)

        if not email_ok and not sms_ok:
            _log.info(
                "[orquestracao] verificar-creditos skip fornecedor_id=%s motivo=sem_canal_email_nem_sms",
                fid,
            )
            ignorados += 1
            continue

        ultimo = snap.ultimo_lembrete_limite_semanal_em
        if ultimo is not None:
            ref = datetime.now(UTC)
            lim = ultimo if ultimo.tzinfo else ultimo.replace(tzinfo=UTC)
            if ref - lim < timedelta(days=7):
                _log.info(
                    "[orquestracao] verificar-creditos skip fornecedor_id=%s cadencia_7d ultimo=%s",
                    fid,
                    ultimo,
                )
                ignorados += 1
                continue

        ext = str(uuid.uuid4())

        if creditos_restantes == 0:
            tpl = CodigoTipoTemplate.LEMBRETE_CREDITOS_ESGOTADOS
            _log.info(
                "[orquestracao] verificar-creditos fornecedor_id=%s ramo=zerados template=%s",
                fid,
                tpl.value,
            )
            ok = False
            if email_ok:
                pedido = montar_pedido_email_creditos_esgotados(
                    destinatario=email,
                    fornecedor_id=fid,
                    id_externo=ext,
                    nome_fantasia=nome,
                    link_creditos=link_creditos,
                )
                ok = await enfileirar_email_pendente(redis, pedido, id_externo=ext, origem=_ORIGEM)
            elif sms_ok:
                pedido_s = montar_pedido_sms_creditos_esgotados(
                    destinatario=telefone,
                    fornecedor_id=fid,
                    id_externo=ext,
                    nome_fantasia=nome,
                    link_creditos=link_creditos,
                )
                ok = await enfileirar_sms_pendente(redis, pedido_s, id_externo=ext, origem=_ORIGEM)
            if ok:
                await registrar_lembrete_creditos_semanal(pool, fid)
                enfileirados += 1
            else:
                ignorados += 1
            continue

        if 0 < creditos_restantes <= limiar:
            tpl = CodigoTipoTemplate.CREDITOS_NO_FIM
            _log.info(
                "[orquestracao] verificar-creditos fornecedor_id=%s ramo=no_fim template=%s creditos=%s",
                fid,
                tpl.value,
                creditos_restantes,
            )
            ok = False
            if email_ok:
                pedido = montar_pedido_email_creditos_no_fim(
                    destinatario=email,
                    fornecedor_id=fid,
                    id_externo=ext,
                    nome_fantasia=nome,
                    link_creditos=link_creditos,
                )
                ok = await enfileirar_email_pendente(redis, pedido, id_externo=ext, origem=_ORIGEM)
            elif sms_ok:
                pedido_s = montar_pedido_sms_creditos_no_fim(
                    destinatario=telefone,
                    fornecedor_id=fid,
                    id_externo=ext,
                    nome_fantasia=nome,
                    link_creditos=link_creditos,
                )
                ok = await enfileirar_sms_pendente(redis, pedido_s, id_externo=ext, origem=_ORIGEM)
            if ok:
                await registrar_lembrete_creditos_semanal(pool, fid)
                enfileirados += 1
            else:
                ignorados += 1
            continue

    _log.info(
        "[orquestracao] verificar-creditos fim avaliados=%s enfileirados=%s ignorados=%s",
        len(rows),
        enfileirados,
        ignorados,
    )
    return RespostaVerificarCreditos(
        avaliados=len(rows),
        enfileirados=enfileirados,
        ignorados=ignorados,
    )

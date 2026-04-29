from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

import asyncpg
from redis.asyncio import Redis

from app.orquestracao.api.dto.verificar_creditos_dto import RespostaVerificarCreditos, VerificarCreditosCorpo
from app.orquestracao.repositorios.engajamento_consulta_repo import (
    carregar_para_usuario,
    registrar_lembrete_creditos_semanal,
)
from app.orquestracao.servicos.auxiliares.enfileirar_ou_enviar_interno import enfileirar_email_pendente
from app.orquestracao.servicos.auxiliares.montar_pedido_mensagem import (
    montar_pedido_email_creditos_esgotados,
    montar_pedido_email_creditos_no_fim,
)
from app.templates.modelo import CodigoTipoTemplate

_log = logging.getLogger(__name__)
_ORIGEM = "orquestracao-verificar-creditos"


async def executar_verificar_creditos(
    pool: asyncpg.Pool,
    redis: Redis,
    corpo: VerificarCreditosCorpo,
) -> RespostaVerificarCreditos:
    _log.info(
        "[orquestracao] verificar-creditos inicio usuario_id=%s restantes=%s limiar=%s",
        corpo.usuario_id,
        corpo.creditos_restantes,
        corpo.limiar_creditos_no_fim,
    )

    snap = await carregar_para_usuario(pool, corpo.usuario_id)
    if not snap.recebe_email:
        _log.info("[orquestracao] verificar-creditos fim: recebe_email=false")
        return RespostaVerificarCreditos(acao="nada", motivo="recebe_email=false")

    ultimo = snap.ultimo_lembrete_limite_semanal_em
    if ultimo is not None:
        ref = datetime.now(UTC)
        lim = ultimo if ultimo.tzinfo else ultimo.replace(tzinfo=UTC)
        if ref - lim < timedelta(days=7):
            _log.info(
                "[orquestracao] verificar-creditos fim: cadencia 7d (ultimo_lembrete=%s)",
                ultimo,
            )
            return RespostaVerificarCreditos(acao="nada", motivo="cadência lembrete créditos < 7 dias")

    ext = str(uuid.uuid4())

    if corpo.creditos_restantes == 0:
        _log.info("[orquestracao] verificar-creditos ramo: creditos zerados -> LEMBRETE_CREDITOS_ESGOTADOS")
        pedido = montar_pedido_email_creditos_esgotados(
            destinatario=str(corpo.email_destinatario),
            usuario_id=corpo.usuario_id,
            id_externo=ext,
            nome_fantasia=corpo.nome_fantasia,
            link_creditos=corpo.link_area_creditos,
        )
        ok = await enfileirar_email_pendente(redis, pedido, id_externo=ext, origem=_ORIGEM)
        if ok:
            await registrar_lembrete_creditos_semanal(pool, corpo.usuario_id)
        _log.info("[orquestracao] verificar-creditos fim: enfileirado=%s id_externo=%s", ok, ext)
        return RespostaVerificarCreditos(
            acao="email_enfileirado" if ok else "nada",
            tipo_template=CodigoTipoTemplate.LEMBRETE_CREDITOS_ESGOTADOS.value if ok else None,
            id_externo=ext if ok else None,
            motivo="" if ok else "fila e-mail ocupada para id_externo",
        )

    if 0 < corpo.creditos_restantes <= corpo.limiar_creditos_no_fim:
        _log.info("[orquestracao] verificar-creditos ramo: no fim -> CREDITOS_NO_FIM")
        pedido = montar_pedido_email_creditos_no_fim(
            destinatario=str(corpo.email_destinatario),
            usuario_id=corpo.usuario_id,
            id_externo=ext,
            nome_fantasia=corpo.nome_fantasia,
            link_creditos=corpo.link_area_creditos,
        )
        ok = await enfileirar_email_pendente(redis, pedido, id_externo=ext, origem=_ORIGEM)
        if ok:
            await registrar_lembrete_creditos_semanal(pool, corpo.usuario_id)
        _log.info("[orquestracao] verificar-creditos fim: enfileirado=%s id_externo=%s", ok, ext)
        return RespostaVerificarCreditos(
            acao="email_enfileirado" if ok else "nada",
            tipo_template=CodigoTipoTemplate.CREDITOS_NO_FIM.value if ok else None,
            id_externo=ext if ok else None,
            motivo="" if ok else "fila e-mail ocupada para id_externo",
        )

    _log.info("[orquestracao] verificar-creditos fim: acima do limiar, nada a enviar")
    return RespostaVerificarCreditos(acao="nada", motivo="créditos acima do limiar de aviso")

"""Enfileira o próximo e-mail (fila pré-envio) a partir de metadados do Redis ou sweep."""

from __future__ import annotations

import json
import logging
import uuid

from redis.asyncio import Redis

from app.mensageria.api.dto.modelos import PedidoEnvioEmail
from app.orquestracao.repositorios.engajamento_consulta_repo import SnapshotEngajamentoOrquestracao
from app.orquestracao.repositorios.redis_emails_pendentes_repo import RepositorioEmailsPendenteRedis
from app.reenvio.repositorios.redis_consulta_notificacao import parse_consulta_id_hash
from app.reenvio.repositorios.redis_emails_esperando_confirmacao import RepositorioEmailsEsperandoConfirmacaoRedis
from app.reenvio.servicos.engajamento_contatos import agregado_canal_bloqueado, proximo_email_tentavel_apos_contato
from app.reenvio.servicos.engajamento_fornecedor import parse_fornecedor_id
from app.templates.modelo import CodigoTipoTemplate

_log = logging.getLogger(__name__)


def pedido_envio_email_de_metadados_redis(
    dados: dict[str, str],
    *,
    destinatario: str,
    novo_id_externo: str,
) -> PedidoEnvioEmail:
    ctx_raw = dados.get("contexto_json") or "{}"
    try:
        base = json.loads(ctx_raw)
    except json.JSONDecodeError:
        base = {}
    if not isinstance(base, dict):
        base = {}
    ctx = {str(k): str(v) for k, v in base.items() if v is not None}
    tipo_s = (dados.get("tipo_template") or "").strip()
    tipo = CodigoTipoTemplate(tipo_s)
    uid = parse_fornecedor_id((dados.get("fornecedor_id") or dados.get("usuario_id") or "").strip())
    cnpj = (dados.get("cnpj_basico") or "").strip() or None
    cid = parse_consulta_id_hash(dados.get("consulta_id"))
    rem = (dados.get("remetente") or "").strip() or None
    return PedidoEnvioEmail(
        destinatario=destinatario,
        tipo_template=tipo,
        contexto=ctx,
        remetente=rem,
        id_externo=novo_id_externo,
        fornecedor_id=uid,
        cnpj_basico=cnpj,
        consulta_id=cid,
    )


async def tentar_enfileirar_proximo_email_engajamento(
    redis: Redis,
    dados: dict[str, str],
    snap: SnapshotEngajamentoOrquestracao,
    *,
    email_atual: str | None,
    origem: str,
    message_id_esperando: str | None = None,
) -> str | None:
    """Se houver próximo e-mail tentável e o agregado de e-mail não estiver inativo, enfileira e devolve o novo ``id_externo``.

    Quando ``message_id_esperando`` é informado (envio atual em ``emails-esperando-confirmacao``), remove essa
    entrada **antes** de criar o pendente, liberando a trava NX da consulta (``ConsultaJaNotificadaError``).
    """
    if agregado_canal_bloqueado(snap.engajamento_email):
        return None
    prox = proximo_email_tentavel_apos_contato(snap.contatos_email, email_atual)
    if not prox:
        return None
    if message_id_esperando:
        await RepositorioEmailsEsperandoConfirmacaoRedis().remover(redis, message_id_esperando)
    novo = str(uuid.uuid4())
    pedido = pedido_envio_email_de_metadados_redis(dados, destinatario=prox, novo_id_externo=novo)
    repo = RepositorioEmailsPendenteRedis()
    ok = await repo.criar(
        redis,
        id_externo=novo,
        destinatario=pedido.destinatario,
        tipo_template=pedido.tipo_template.value,
        contexto=dict(pedido.contexto),
        remetente=pedido.remetente,
        fornecedor_id=str(pedido.fornecedor_id) if pedido.fornecedor_id else None,
        cnpj_basico=pedido.cnpj_basico,
        consulta_id=pedido.consulta_id,
        origem=origem,
    )
    if ok:
        _log.info(
            "Próximo e-mail enfileirado: id_externo=%s dest=%s origem=%s",
            novo,
            prox,
            origem,
        )
        return novo
    _log.warning("Fila e-mail pendente não aceitou novo id_externo=%s (possível duplicata)", novo)
    return None

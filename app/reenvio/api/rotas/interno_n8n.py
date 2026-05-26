from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from redis.asyncio import Redis

from app.iam.dependencias import verificar_chamada_interna
from app.orquestracao.repositorios.redis_emails_pendentes_repo import (
    RepositorioEmailsPendenteRedis,
    chave_hash as chave_hash_email_pendente,
)
from app.reenvio.api.dto.n8n import (
    ItemPendenteN8N,
    PedidoClaimN8N,
    PedidoConfirmarConsumoN8N,
    RespostaClaimN8N,
    RespostaConfirmarConsumoN8N,
    RespostaItensPendentesN8N,
)
from app.reenvio.redis_app import obter_cliente_redis
from app.reenvio.repositorios.redis_sms_pendente import (
    RepositorioSmsPendenteRedis,
    chave_hash as chave_hash_sms_pendente,
)
from app.reenvio.servicos.n8n_claims import (
    CLAIM_TTL_PADRAO_SEGUNDOS,
    liberar_claim_item_n8n,
    tentar_claim_item_n8n,
)

router = APIRouter(
    prefix="/v1/interno/n8n",
    tags=["interno-n8n"],
    dependencies=[Depends(verificar_chamada_interna)],
)


async def _redis() -> Redis:
    return await obter_cliente_redis()


def _limitar_lote(limite: int) -> int:
    return max(1, min(limite, 500))


def _montar_payload_envio(item: dict[str, Any], *, destinatario: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "destinatario": destinatario,
        "tipo_template": item.get("tipo_template", ""),
        "contexto": item.get("contexto") if isinstance(item.get("contexto"), dict) else {},
        "id_externo": item.get("id_externo"),
    }
    for campo in ("remetente", "fornecedor_id", "cnpj_basico", "consulta_id"):
        valor = item.get(campo)
        if valor:
            payload[campo] = valor
    return payload


def _serializar_item_email(item: dict[str, Any]) -> ItemPendenteN8N:
    destinatario = item.get("destinatario", "")
    return ItemPendenteN8N(
        canal="email",
        id_externo=item.get("id_externo", ""),
        destinatario=destinatario,
        tipo_template=item.get("tipo_template", ""),
        contexto=item.get("contexto") if isinstance(item.get("contexto"), dict) else {},
        remetente=item.get("remetente"),
        fornecedor_id=item.get("fornecedor_id"),
        cnpj_basico=item.get("cnpj_basico"),
        consulta_id=item.get("consulta_id"),
        origem=item.get("origem", ""),
        criado_em=item.get("criado_em"),
        payload_envio=_montar_payload_envio(item, destinatario=destinatario),
    )


def _serializar_item_sms(item: dict[str, Any]) -> ItemPendenteN8N:
    destinatario = item.get("telefone", "")
    return ItemPendenteN8N(
        canal="sms",
        id_externo=item.get("id_externo", ""),
        destinatario=destinatario,
        tipo_template=item.get("tipo_template", ""),
        contexto=item.get("contexto") if isinstance(item.get("contexto"), dict) else {},
        remetente=item.get("remetente"),
        fornecedor_id=item.get("fornecedor_id"),
        cnpj_basico=item.get("cnpj_basico"),
        consulta_id=item.get("consulta_id"),
        origem=item.get("origem", ""),
        criado_em=item.get("criado_em"),
        payload_envio=_montar_payload_envio(item, destinatario=destinatario),
    )


async def _claim_itens(
    redis: Redis,
    *,
    canal: str,
    itens: list[ItemPendenteN8N],
    limite: int,
) -> list[ItemPendenteN8N]:
    saida: list[ItemPendenteN8N] = []
    for item in itens:
        if len(saida) >= limite:
            break
        if not item.id_externo:
            continue
        conseguiu = await tentar_claim_item_n8n(
            redis,
            canal=canal,
            id_externo=item.id_externo,
            ttl_segundos=CLAIM_TTL_PADRAO_SEGUNDOS,
        )
        if conseguiu:
            saida.append(item)
    return saida


@router.get(
    "/emails-pendentes",
    response_model=RespostaItensPendentesN8N,
    status_code=status.HTTP_200_OK,
    summary="Lista e-mails pendentes para integracao com n8n",
)
async def get_emails_pendentes_n8n(
    redis: Annotated[Redis, Depends(_redis)],
    limite: Annotated[int, Query(ge=1, le=500)] = 200,
) -> RespostaItensPendentesN8N:
    repo = RepositorioEmailsPendenteRedis()
    itens = await repo.listar_pendentes(redis, limite=_limitar_lote(limite))
    serializados = [_serializar_item_email(item) for item in itens]
    return RespostaItensPendentesN8N(total=len(serializados), itens=serializados)


@router.get(
    "/sms-pendentes",
    response_model=RespostaItensPendentesN8N,
    status_code=status.HTTP_200_OK,
    summary="Lista SMS pendentes para integracao com n8n",
)
async def get_sms_pendentes_n8n(
    redis: Annotated[Redis, Depends(_redis)],
    limite: Annotated[int, Query(ge=1, le=500)] = 200,
) -> RespostaItensPendentesN8N:
    repo = RepositorioSmsPendenteRedis()
    itens = await repo.listar_pendentes(redis, limite=_limitar_lote(limite))
    serializados = [_serializar_item_sms(item) for item in itens]
    return RespostaItensPendentesN8N(total=len(serializados), itens=serializados)


@router.post(
    "/emails-pendentes/claim",
    response_model=RespostaClaimN8N,
    status_code=status.HTTP_200_OK,
    summary="Reserva temporariamente e-mails pendentes para o n8n (mais antigos primeiro)",
)
async def post_claim_emails_pendentes_n8n(
    pedido: PedidoClaimN8N,
    redis: Annotated[Redis, Depends(_redis)],
) -> RespostaClaimN8N:
    repo = RepositorioEmailsPendenteRedis()
    itens = await repo.listar_pendentes(redis, limite=_limitar_lote(pedido.limite * 5))
    serializados = [_serializar_item_email(item) for item in itens]
    claimados = await _claim_itens(redis, canal="email", itens=serializados, limite=pedido.limite)
    return RespostaClaimN8N(
        total=len(claimados),
        itens=claimados,
        ttl_claim_segundos=CLAIM_TTL_PADRAO_SEGUNDOS,
    )


@router.post(
    "/emails-pendentes/claim-recentes",
    response_model=RespostaClaimN8N,
    status_code=status.HTTP_200_OK,
    summary="Reserva temporariamente e-mails pendentes para o n8n (mais recentes primeiro)",
)
async def post_claim_emails_pendentes_recentes_n8n(
    pedido: PedidoClaimN8N,
    redis: Annotated[Redis, Depends(_redis)],
) -> RespostaClaimN8N:
    repo = RepositorioEmailsPendenteRedis()
    itens = await repo.listar_pendentes_recentes(redis, limite=_limitar_lote(pedido.limite * 5))
    serializados = [_serializar_item_email(item) for item in itens]
    claimados = await _claim_itens(redis, canal="email", itens=serializados, limite=pedido.limite)
    return RespostaClaimN8N(
        total=len(claimados),
        itens=claimados,
        ttl_claim_segundos=CLAIM_TTL_PADRAO_SEGUNDOS,
    )


@router.post(
    "/sms-pendentes/claim",
    response_model=RespostaClaimN8N,
    status_code=status.HTTP_200_OK,
    summary="Reserva temporariamente SMS pendentes para o n8n (mais antigos primeiro)",
)
async def post_claim_sms_pendentes_n8n(
    pedido: PedidoClaimN8N,
    redis: Annotated[Redis, Depends(_redis)],
) -> RespostaClaimN8N:
    repo = RepositorioSmsPendenteRedis()
    itens = await repo.listar_pendentes(redis, limite=_limitar_lote(pedido.limite * 5))
    serializados = [_serializar_item_sms(item) for item in itens]
    claimados = await _claim_itens(redis, canal="sms", itens=serializados, limite=pedido.limite)
    return RespostaClaimN8N(
        total=len(claimados),
        itens=claimados,
        ttl_claim_segundos=CLAIM_TTL_PADRAO_SEGUNDOS,
    )


@router.post(
    "/sms-pendentes/claim-recentes",
    response_model=RespostaClaimN8N,
    status_code=status.HTTP_200_OK,
    summary="Reserva temporariamente SMS pendentes para o n8n (mais recentes primeiro)",
)
async def post_claim_sms_pendentes_recentes_n8n(
    pedido: PedidoClaimN8N,
    redis: Annotated[Redis, Depends(_redis)],
) -> RespostaClaimN8N:
    repo = RepositorioSmsPendenteRedis()
    itens = await repo.listar_pendentes_recentes(redis, limite=_limitar_lote(pedido.limite * 5))
    serializados = [_serializar_item_sms(item) for item in itens]
    claimados = await _claim_itens(redis, canal="sms", itens=serializados, limite=pedido.limite)
    return RespostaClaimN8N(
        total=len(claimados),
        itens=claimados,
        ttl_claim_segundos=CLAIM_TTL_PADRAO_SEGUNDOS,
    )


@router.post(
    "/emails-pendentes/confirmar-consumo",
    response_model=RespostaConfirmarConsumoN8N,
    status_code=status.HTTP_200_OK,
    summary="Confirma consumo de e-mail pendente e remove da fila",
)
async def post_confirmar_consumo_email_n8n(
    pedido: PedidoConfirmarConsumoN8N,
    redis: Annotated[Redis, Depends(_redis)],
) -> RespostaConfirmarConsumoN8N:
    repo = RepositorioEmailsPendenteRedis()
    existe = bool(await redis.exists(chave_hash_email_pendente(pedido.id_externo)))
    if existe:
        await repo.remover(redis, pedido.id_externo)
        status_remocao = "removido"
    else:
        status_remocao = "ja_nao_existia"
    await liberar_claim_item_n8n(redis, canal="email", id_externo=pedido.id_externo)
    return RespostaConfirmarConsumoN8N(id_externo=pedido.id_externo, status=status_remocao)


@router.post(
    "/sms-pendentes/confirmar-consumo",
    response_model=RespostaConfirmarConsumoN8N,
    status_code=status.HTTP_200_OK,
    summary="Confirma consumo de SMS pendente e remove da fila",
)
async def post_confirmar_consumo_sms_n8n(
    pedido: PedidoConfirmarConsumoN8N,
    redis: Annotated[Redis, Depends(_redis)],
) -> RespostaConfirmarConsumoN8N:
    repo = RepositorioSmsPendenteRedis()
    existe = bool(await redis.exists(chave_hash_sms_pendente(pedido.id_externo)))
    if existe:
        await repo.remover(redis, pedido.id_externo)
        status_remocao = "removido"
    else:
        status_remocao = "ja_nao_existia"
    await liberar_claim_item_n8n(redis, canal="sms", id_externo=pedido.id_externo)
    return RespostaConfirmarConsumoN8N(id_externo=pedido.id_externo, status=status_remocao)

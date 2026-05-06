"""Trava por consulta: uma notificação orquestrada por `consulta_id` de cada vez (pendente ou esperando)."""
from __future__ import annotations

import uuid

from redis.asyncio import Redis

PREFIXO = "orq:consulta-notificacao"


def chave_trava_consulta(consulta_id: uuid.UUID) -> str:
    return f"{PREFIXO}:{consulta_id}"


def fase_pendente_email(id_externo: str) -> str:
    return f"pendente-email:{id_externo}"


def fase_esperando_email(message_id: str) -> str:
    return f"esperando-email:{message_id}"


def fase_esperando_sms(message_id: str) -> str:
    return f"esperando-sms:{message_id}"


def fase_pendente_sms(id_externo: str) -> str:
    return f"pendente-sms:{id_externo}"


async def consulta_tem_trava_ativa(redis: Redis, consulta_id: uuid.UUID) -> bool:
    return bool(await redis.exists(chave_trava_consulta(consulta_id)))


async def tentar_travar_pendente_email(redis: Redis, consulta_id: uuid.UUID, id_externo: str) -> bool:
    """True se esta instância ganhou a trava (SET NX)."""
    return bool(
        await redis.set(chave_trava_consulta(consulta_id), fase_pendente_email(id_externo), nx=True),
    )


async def tentar_travar_pendente_sms(redis: Redis, consulta_id: uuid.UUID, id_externo: str) -> bool:
    return bool(
        await redis.set(chave_trava_consulta(consulta_id), fase_pendente_sms(id_externo), nx=True),
    )


async def promover_para_esperando_email(redis: Redis, consulta_id: uuid.UUID | None, message_id: str) -> None:
    if consulta_id is None:
        return
    await redis.set(chave_trava_consulta(consulta_id), fase_esperando_email(message_id))


async def promover_para_esperando_sms(redis: Redis, consulta_id: uuid.UUID | None, message_id: str) -> None:
    if consulta_id is None:
        return
    await redis.set(chave_trava_consulta(consulta_id), fase_esperando_sms(message_id))


async def redefinir_para_pendente_sms_pos_bounce(redis: Redis, consulta_id: uuid.UUID | None, id_externo: str) -> None:
    """Sobrescreve a trava (e-mail esperando → SMS pendente após bounce / sweep)."""
    if consulta_id is None:
        return
    await redis.set(chave_trava_consulta(consulta_id), fase_pendente_sms(id_externo))


async def liberar_trava_se_fase(redis: Redis, consulta_id: uuid.UUID | None, fase_esperada: str) -> None:
    if consulta_id is None:
        return
    key = chave_trava_consulta(consulta_id)
    atual = await redis.get(key)
    if atual == fase_esperada:
        await redis.delete(key)


async def liberar_trava_forcado(redis: Redis, consulta_id: uuid.UUID | None) -> None:
    if consulta_id is None:
        return
    await redis.delete(chave_trava_consulta(consulta_id))


def parse_consulta_id_hash(raw: str | None) -> uuid.UUID | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        return uuid.UUID(s)
    except ValueError:
        return None

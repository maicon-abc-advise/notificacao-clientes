"""Trava por consulta + CNPJ base (8 dígitos): um fluxo orquestrado por par (consulta, fornecedor)."""

from __future__ import annotations

import uuid

from redis.asyncio import Redis

PREFIXO = "orq:consulta-notificacao"


def _chave_trava(consulta_id: uuid.UUID | None, cnpj_basico: str | None) -> str | None:
    """Chave Redis ``orq:consulta-notificacao:{uuid}:{cnpj8}``. Sem par completo → sem trava NX."""
    if consulta_id is None:
        return None
    cnpj = (cnpj_basico or "").strip()
    if len(cnpj) != 8:
        return None
    return f"{PREFIXO}:{consulta_id}:{cnpj}"


def fase_pendente_email(id_externo: str) -> str:
    return f"pendente-email:{id_externo}"


def fase_esperando_email(message_id: str) -> str:
    return f"esperando-email:{message_id}"


def fase_esperando_sms(message_id: str) -> str:
    return f"esperando-sms:{message_id}"


def fase_pendente_sms(id_externo: str) -> str:
    return f"pendente-sms:{id_externo}"


async def consulta_fornecedor_tem_trava_ativa(
    redis: Redis,
    consulta_id: uuid.UUID,
    cnpj_basico: str,
) -> bool:
    key = _chave_trava(consulta_id, cnpj_basico)
    if key is None:
        return False
    return bool(await redis.exists(key))


async def tentar_travar_pendente_email(
    redis: Redis,
    consulta_id: uuid.UUID,
    cnpj_basico: str | None,
    id_externo: str,
) -> bool:
    """True se pode enfileirar: ganhou NX ou não há trava (sem cnpj/consulta incompleto)."""
    key = _chave_trava(consulta_id, cnpj_basico)
    if key is None:
        return True
    return bool(await redis.set(key, fase_pendente_email(id_externo), nx=True))


async def tentar_travar_pendente_sms(
    redis: Redis,
    consulta_id: uuid.UUID,
    cnpj_basico: str | None,
    id_externo: str,
) -> bool:
    key = _chave_trava(consulta_id, cnpj_basico)
    if key is None:
        return True
    return bool(await redis.set(key, fase_pendente_sms(id_externo), nx=True))


async def promover_para_esperando_email(
    redis: Redis,
    consulta_id: uuid.UUID | None,
    cnpj_basico: str | None,
    message_id: str,
) -> None:
    key = _chave_trava(consulta_id, cnpj_basico)
    if key is None:
        return
    await redis.set(key, fase_esperando_email(message_id))


async def promover_para_esperando_sms(
    redis: Redis,
    consulta_id: uuid.UUID | None,
    cnpj_basico: str | None,
    message_id: str,
) -> None:
    key = _chave_trava(consulta_id, cnpj_basico)
    if key is None:
        return
    await redis.set(key, fase_esperando_sms(message_id))


async def redefinir_para_pendente_sms(
    redis: Redis,
    consulta_id: uuid.UUID | None,
    cnpj_basico: str | None,
    id_externo: str,
) -> None:
    """Sobrescreve a trava NX existente para ``pendente-sms:{id_externo}``."""
    key = _chave_trava(consulta_id, cnpj_basico)
    if key is None:
        return
    await redis.set(key, fase_pendente_sms(id_externo))


async def redefinir_para_pendente_sms_pos_bounce(
    redis: Redis,
    consulta_id: uuid.UUID | None,
    cnpj_basico: str | None,
    id_externo: str,
) -> None:
    """Sobrescreve a trava (e-mail esperando → SMS pendente após bounce / sweep de e-mail)."""
    await redefinir_para_pendente_sms(redis, consulta_id, cnpj_basico, id_externo)


async def redefinir_para_pendente_sms_pos_sms_esperando(
    redis: Redis,
    consulta_id: uuid.UUID | None,
    cnpj_basico: str | None,
    id_externo: str,
) -> None:
    """Sobrescreve a trava (``sms-esperando-confirmacao`` → ``sms-pendente`` no sweep SMS)."""
    await redefinir_para_pendente_sms(redis, consulta_id, cnpj_basico, id_externo)


async def liberar_trava_se_fase(
    redis: Redis,
    consulta_id: uuid.UUID | None,
    cnpj_basico: str | None,
    fase_esperada: str,
) -> None:
    key = _chave_trava(consulta_id, cnpj_basico)
    if key is None:
        return
    atual = await redis.get(key)
    atual_s = atual.decode() if isinstance(atual, bytes) else (atual or "")
    if atual_s == fase_esperada:
        await redis.delete(key)


async def liberar_trava_forcado(
    redis: Redis,
    consulta_id: uuid.UUID | None,
    cnpj_basico: str | None,
) -> None:
    key = _chave_trava(consulta_id, cnpj_basico)
    if key is None:
        return
    await redis.delete(key)


def parse_consulta_id_hash(raw: str | None) -> uuid.UUID | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        return uuid.UUID(s)
    except ValueError:
        return None

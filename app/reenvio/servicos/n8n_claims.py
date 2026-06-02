from __future__ import annotations

from redis.asyncio import Redis

CLAIM_TTL_PADRAO_SEGUNDOS = 300


def chave_claim_n8n(canal: str, id_externo: str) -> str:
    return f"n8n:claim:{canal}:{id_externo}"


async def claim_n8n_ativo(redis: Redis, *, canal: str, id_externo: str) -> bool:
    return bool(await redis.exists(chave_claim_n8n(canal, id_externo)))


async def tentar_claim_item_n8n(
    redis: Redis,
    *,
    canal: str,
    id_externo: str,
    ttl_segundos: int = CLAIM_TTL_PADRAO_SEGUNDOS,
) -> bool:
    return bool(
        await redis.set(
            chave_claim_n8n(canal, id_externo),
            "1",
            ex=max(1, ttl_segundos),
            nx=True,
        ),
    )


async def liberar_claim_item_n8n(redis: Redis, *, canal: str, id_externo: str) -> None:
    await redis.delete(chave_claim_n8n(canal, id_externo))

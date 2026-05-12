import uuid
import json
import time
from app.config.config import obter_configuracao
from redis.asyncio import Redis

async def criar_sessao(redis: Redis, login: str) -> str:
    config = obter_configuracao()
    session_id = str(uuid.uuid4())
    chave = f"dashboard:sessao:{session_id}"

    session_data = {
        "login": login,
        "created_at": time.time(),
    }

    await redis.set(
        chave, 
        json.dumps(session_data),
        ex=config.dashboard_session_ttl,
    )

    return session_id

async def obter_sessao(redis: Redis, session_id: str) -> dict | None:
    chave = f"dashboard:sessao:{session_id}"
    session_data = await redis.get(chave)
    if not session_data:
        return None
    return json.loads(session_data)

async def destruir_sessao(redis: Redis, session_id: str) -> None:
    chave = f"dashboard:sessao:{session_id}"
    await redis.delete(chave)
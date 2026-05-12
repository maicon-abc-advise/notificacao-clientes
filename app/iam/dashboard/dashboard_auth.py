from secrets import compare_digest
from fastapi import HTTPException, status
from redis.asyncio import Redis
from app.config.config import obter_configuracao
from app.iam.dashboard.sessao import criar_sessao

def validar_login(login: str, password: str) -> bool:
    cfg = obter_configuracao()

    return (
        compare_digest(login, cfg.dashboard_login)
        and compare_digest(password, cfg.dashboard_password)
    )

async def autenticar(redis: Redis, login: str, password: str) -> str:
    if not validar_login(login, password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Login ou senha inválidos",
        )
    return await criar_sessao(redis, login)
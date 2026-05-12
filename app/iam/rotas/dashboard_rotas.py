from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from redis.asyncio import Redis

from app.config.ambiente import Ambiente
from app.config.config import Configuracao, obter_configuracao
from app.iam.dashboard.dashboard_auth import autenticar
from app.iam.dashboard.sessao import destruir_sessao, obter_sessao
from app.reenvio.redis_app import obter_cliente_redis

async def _redis() -> Redis:
    return await obter_cliente_redis()


class LoginPayload(BaseModel):
    usuario: str
    senha: str

RedisDashboard = Annotated[Redis, Depends(_redis)]
ConfigDashboard = Annotated[Configuracao, Depends(obter_configuracao)]
router = APIRouter(prefix="/v1/dashboard", tags=["dashboard-auth"])


def _cookie_policy(config: Configuracao) -> tuple[bool, str]:
    if config.ambiente == Ambiente.PRODUCAO:
        # Front e API em origens diferentes precisam de cookie cross-site.
        return True, "none"
    return False, "lax"


@router.post("/login")
async def login(
    payload: LoginPayload,
    response: Response,
    redis: RedisDashboard,
    config: ConfigDashboard,
) -> dict[str, bool]:
    sessao_id = await autenticar(redis, payload.usuario, payload.senha)
    cookie_secure, cookie_samesite = _cookie_policy(config)

    response.set_cookie(
        key=config.dashboard_cookie_name,
        value=sessao_id,
        httponly=True,
        secure=cookie_secure,
        samesite=cookie_samesite,
        max_age=config.dashboard_session_ttl,
        path="/",
    )
    return {"ok": True}


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    redis: RedisDashboard,
    config: ConfigDashboard,
) -> dict[str, bool]:
    session_id = request.cookies.get(config.dashboard_cookie_name)
    cookie_secure, cookie_samesite = _cookie_policy(config)
    if session_id:
        await destruir_sessao(redis, session_id)

    response.delete_cookie(
        key=config.dashboard_cookie_name,
        path="/",
        secure=cookie_secure,
        httponly=True,
        samesite=cookie_samesite,
    )
    return {"ok": True}


async def usuario_logado(
    redis: RedisDashboard,
    request: Request,
) -> dict[str, Any]:
    config = obter_configuracao()
    session_id = request.cookies.get(config.dashboard_cookie_name)
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão ausente",
        )

    sessao = await obter_sessao(redis, session_id)
    if not sessao:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão inválida",
        )

    return sessao


@router.get("/session")
async def session_atual(
    sessao: Annotated[dict[str, Any], Depends(usuario_logado)],
) -> dict[str, Any]:
    return {"autenticado": True, "sessao": sessao}



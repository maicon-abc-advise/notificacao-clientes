from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from redis.asyncio import Redis

from app.config.config import Configuracao, obter_configuracao
from app.iam.dependencias import verificar_chamada_interna
from app.iam.rotas.dashboard_rotas import usuario_logado
from app.ligacoes.api.dto.modelos import PedidoDisparoLigacao
from app.ligacoes.api.externo.vapi.adaptador_envio import ErroEnvioVapi
from app.ligacoes.repositorios.redis_webhook_debug import listar_eventos_webhook
from app.ligacoes.servicos.executar_dispatch_call import executar_dispatch_call
from app.orquestracao.api.dependencias import PoolOrquestracao
from app.reenvio.redis_app import obter_cliente_redis

router_disparar = APIRouter(
    prefix="/v1/ligacoes",
    tags=["ligações"],
    dependencies=[Depends(verificar_chamada_interna)],
)

router_dashboard = APIRouter(
    prefix="/v1/interno/dashboard/ligacoes",
    tags=["dashboard — ligações"],
    dependencies=[Depends(usuario_logado)],
)


async def _redis() -> Redis:
    return await obter_cliente_redis()


@router_disparar.post("/disparar", status_code=status.HTTP_201_CREATED)
async def post_disparar_ligacao(
    pedido: PedidoDisparoLigacao,
    pool: PoolOrquestracao,
    config: Annotated[Configuracao, Depends(obter_configuracao)],
) -> dict[str, Any]:
    """Protótipo legado — preferir ``POST /v1/calls/dispatch``."""
    try:
        return await executar_dispatch_call(pool, pedido, config=config)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except ErroEnvioVapi as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e)[:2000],
        ) from e


@router_dashboard.get("/webhook-eventos")
async def get_webhook_eventos(
    redis: Annotated[Redis, Depends(_redis)],
    limite: int = Query(default=100, ge=1, le=200),
) -> dict[str, Any]:
    eventos = await listar_eventos_webhook(redis, limite=limite)
    return {"total": len(eventos), "eventos": eventos}

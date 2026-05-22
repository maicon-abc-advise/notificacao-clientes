"""GET público: valida token, registra primeiro clique e devolve JSON para o front."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from redis.asyncio import Redis

from app.clique.api.dto_clique import DadosCliqueResposta
from app.clique.servicos.registrar_clique import (
    montar_redirect_para_id_externo,
    processar_clique_api,
)
from app.clique.token_clique import TAMANHO_TOKEN_URL, decifrar_url_para_id
from app.config.config import Configuracao, obter_configuracao
from app.reenvio.redis_app import obter_cliente_redis
from app.templates.conexao import obter_pool

router = APIRouter(prefix="/v1/clique", tags=["clique — link rastreado"])


async def _redis() -> Redis:
    return await obter_cliente_redis()


@router.get(
    "/{token}",
    response_model=DadosCliqueResposta,
    summary="Clique no link da mensagem (JSON para /info-consulta no Lovable)",
)
async def get_clique_dados(
    token: str,
    redis: Annotated[Redis, Depends(_redis)],
    config: Annotated[Configuracao, Depends(obter_configuracao)],
    redirect: Annotated[
        bool,
        Query(
            description="Se true, responde 302 para a landing (legado/debug). Padrão: JSON.",
        ),
    ] = False,
) -> DadosCliqueResposta | RedirectResponse:
    if len(token) != TAMANHO_TOKEN_URL:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link inválido ou expirado")
    id_externo = decifrar_url_para_id(token, config.link_clique_secret)
    if not id_externo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link inválido ou expirado")

    pool = await obter_pool()

    if redirect:
        destino = await montar_redirect_para_id_externo(pool, config, id_externo)
        if destino is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Envio não encontrado")
        await processar_clique_api(pool, redis, id_externo)
        return RedirectResponse(url=destino, status_code=status.HTTP_302_FOUND)

    dados = await processar_clique_api(pool, redis, id_externo)
    if dados is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Envio não encontrado")

    return DadosCliqueResposta(**dados)

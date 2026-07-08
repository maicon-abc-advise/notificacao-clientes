from __future__ import annotations

from fastapi import APIRouter, status

from app.orquestracao.api.dependencias import PoolOrquestracao
from app.orquestracao.api.dto.sincronizar_conversoes_compradores_dto import (
    RespostaSincronizarConversoesCompradores,
)
from app.orquestracao.servicos.sincronizar_conversoes_compradores_servico import (
    executar_sincronizar_conversoes_compradores,
)

router = APIRouter()


@router.post(
    "/sincronizar-conversoes-compradores",
    response_model=RespostaSincronizarConversoesCompradores,
    status_code=status.HTTP_200_OK,
    summary="Marca compradores elegíveis como convertidos se n_acessos > 1 em usuario_comprador",
)
async def post_sincronizar_conversoes_compradores(
    pool: PoolOrquestracao,
) -> RespostaSincronizarConversoesCompradores:
    return await executar_sincronizar_conversoes_compradores(pool)

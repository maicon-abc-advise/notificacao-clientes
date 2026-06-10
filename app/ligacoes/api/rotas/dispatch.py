from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.config.config import Configuracao, obter_configuracao
from app.iam.dependencias import verificar_chamada_interna
from app.ligacoes.api.dto.modelos import PedidoDisparoLigacao
from app.ligacoes.api.externo.vapi.adaptador_envio import ErroEnvioVapi
from app.ligacoes.servicos.executar_dispatch_call import executar_dispatch_call
from app.orquestracao.api.dependencias import PoolOrquestracao

router = APIRouter(
    prefix="/v1/calls",
    tags=["ligações"],
    dependencies=[Depends(verificar_chamada_interna)],
)


@router.post("/dispatch", status_code=status.HTTP_201_CREATED)
async def post_dispatch_call(
    pedido: PedidoDisparoLigacao,
    pool: PoolOrquestracao,
    config: Annotated[Configuracao, Depends(obter_configuracao)],
) -> dict[str, Any]:
    try:
        return await executar_dispatch_call(pool, pedido, config=config)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except ErroEnvioVapi as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e)[:2000],
        ) from e

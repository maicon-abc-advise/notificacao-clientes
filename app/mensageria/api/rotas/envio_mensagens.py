from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.config.dependencias import obter_porta_envio_mensagem
from app.config.dependencias_templates import PortaTemplatesDep
from app.iam.dependencias import verificar_chamada_interna
from app.mensageria.api.dto.modelos import (
    PedidoEnvioEmail,
    PedidoEnvioSms,
    ResultadoEnvioMensagem,
)
from app.mensageria.excecoes.erro import ErroEnvioZenvia
from app.mensageria.servicos.materializar import materializar_email, materializar_sms
from app.mensageria.servicos.porta import PortaEnvioMensagem

router = APIRouter(
    prefix="/v1/mensagens",
    dependencies=[Depends(verificar_chamada_interna)],
)


@router.post("/email", response_model=ResultadoEnvioMensagem, status_code=status.HTTP_200_OK)
async def post_enviar_email(
    pedido: PedidoEnvioEmail,
    porta: Annotated[PortaEnvioMensagem, Depends(obter_porta_envio_mensagem)],
    templates: PortaTemplatesDep,
) -> ResultadoEnvioMensagem:
    try:
        materializado = await materializar_email(pedido, templates)
        return porta.enviar_email(materializado)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except ErroEnvioZenvia as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e)[:2000],
        ) from e


@router.post("/sms", response_model=ResultadoEnvioMensagem, status_code=status.HTTP_200_OK)
async def post_enviar_sms(
    pedido: PedidoEnvioSms,
    porta: Annotated[PortaEnvioMensagem, Depends(obter_porta_envio_mensagem)],
    templates: PortaTemplatesDep,
) -> ResultadoEnvioMensagem:
    try:
        materializado = await materializar_sms(pedido, templates)
        return porta.enviar_sms(materializado)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except ErroEnvioZenvia as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e)[:2000],
        ) from e

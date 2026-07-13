from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.config.dependencias import obter_porta_envio_mensagem
from app.config.dependencias_templates import PortaTemplatesDep
from app.mensageria.servicos.porta import PortaEnvioMensagem
from app.orquestracao.api.dependencias import PoolOrquestracao
from app.orquestracao.api.dto.codigo_verificacao_dto import (
    PedidoSmsCodigoVerificacao,
    RespostaSmsCodigoVerificacao,
)
from app.orquestracao.servicos.enviar_sms_codigo_verificacao import (
    executar_envio_sms_codigo_verificacao,
)

router = APIRouter()


@router.post(
    "/codigo-verificacao/sms",
    response_model=RespostaSmsCodigoVerificacao,
    status_code=status.HTTP_200_OK,
    summary="Envia SMS com código de verificação",
)
async def post_sms_codigo_verificacao(
    corpo: PedidoSmsCodigoVerificacao,
    pool: PoolOrquestracao,
    porta: Annotated[PortaEnvioMensagem, Depends(obter_porta_envio_mensagem)],
    templates: PortaTemplatesDep,
) -> RespostaSmsCodigoVerificacao:
    return await executar_envio_sms_codigo_verificacao(
        pool,
        corpo,
        porta=porta,
        templates=templates,
    )

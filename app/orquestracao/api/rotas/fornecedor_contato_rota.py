from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.config.dependencias import obter_porta_envio_mensagem
from app.config.dependencias_templates import PortaTemplatesDep
from app.mensageria.servicos.porta import PortaEnvioMensagem
from app.orquestracao.api.dependencias import PoolOrquestracao, PortaEnriquecimento
from app.orquestracao.api.dto.fornecedor_contato_dto import (
    PedidoEmailFornecedorContato,
    RespostaEmailFornecedorContato,
)
from app.orquestracao.excecoes import ConsultaNaoEncontradaError
from app.orquestracao.servicos.enviar_email_fornecedor_contato import (
    executar_envio_email_fornecedor_contato,
)

router = APIRouter()


@router.post(
    "/fornecedor-contato/email",
    response_model=RespostaEmailFornecedorContato,
    status_code=status.HTTP_200_OK,
    summary="Envia e-mail de contato do comprador ao fornecedor",
)
async def post_email_fornecedor_contato(
    corpo: PedidoEmailFornecedorContato,
    pool: PoolOrquestracao,
    porta_enriquecimento: PortaEnriquecimento,
    porta: Annotated[PortaEnvioMensagem, Depends(obter_porta_envio_mensagem)],
    templates: PortaTemplatesDep,
) -> RespostaEmailFornecedorContato:
    try:
        return await executar_envio_email_fornecedor_contato(
            pool,
            porta_enriquecimento,
            corpo,
            porta=porta,
            templates=templates,
        )
    except ConsultaNaoEncontradaError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

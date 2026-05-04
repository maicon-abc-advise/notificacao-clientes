from typing import Annotated
from fastapi import Depends, HTTPException
from app.config.config import Configuracao, obter_configuracao
from app.mensageria.excecoes.erro_provedor import FalhaConfiguracaoProvedor
from app.mensageria.servicos.fabrica_provedor_mensagem import construir_porta_mensagem
from app.mensageria.servicos.porta import PortaEnvioMensagem


def obter_porta_envio_mensagem(
    config: Annotated[Configuracao, Depends(obter_configuracao)],
) -> PortaEnvioMensagem:
    try:
        return construir_porta_mensagem(config)
    except FalhaConfiguracaoProvedor as e:
        raise HTTPException(status_code=e.status_code, detail=e.detalhe) from e

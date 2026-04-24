from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from app.excecoes.erro_provedor import FalhaConfiguracaoProvedor
from app.servicos.mensageria.fabrica_provedor_mensagem import construir_porta_mensagem
from app.servicos.mensageria.porta import PortaEnvioMensagem
from app.config.config import Configuracao, obter_configuracao
from app.config.security import exigir_api_key

_bearer = HTTPBearer(auto_error=False)
_cabecalho_api_key = APIKeyHeader(name="X-Api-Key", auto_error=False)


async def verificar_chamada_interna(
    config: Annotated[Configuracao, Depends(obter_configuracao)],
    credencial_bearer: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)],
    x_api_key: Annotated[str | None, Security(_cabecalho_api_key)],
) -> None:

    token: str | None = None
    if credencial_bearer and credencial_bearer.scheme.lower() == "bearer":
        token = credencial_bearer.credentials
    elif x_api_key:
        token = x_api_key
    exigir_api_key(token, config.api_key)

# Função criada para obter a porta de envio de mensagem
def obter_porta_envio_mensagem(
    config: Annotated[Configuracao, Depends(obter_configuracao)],
) -> PortaEnvioMensagem:
    try:
        return construir_porta_mensagem(config)
    except FalhaConfiguracaoProvedor as e:
        raise HTTPException(status_code=e.status_code, detail=e.detalhe) from e

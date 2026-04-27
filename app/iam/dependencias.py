from typing import Annotated

from fastapi import Depends, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from app.config.config import Configuracao, obter_configuracao
from app.iam.security import exigir_api_key

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

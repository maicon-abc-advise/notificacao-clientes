from secrets import compare_digest
from fastapi import HTTPException, status

def exigir_api_key(valor_recebido: str | None, api_key_servidor: str) -> None:

    if not valor_recebido:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credencial ausente",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not api_key_servidor:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API_KEY não configurada no servidor",
        )

    if not compare_digest(valor_recebido, api_key_servidor):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credencial inválida",
            headers={"WWW-Authenticate": "Bearer"},
        )

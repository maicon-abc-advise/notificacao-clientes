from __future__ import annotations
from typing import Annotated
from fastapi import Depends, HTTPException, status
from app.config.config import Configuracao, obter_configuracao


async def exigir_teste_pipeline_habilitado(
    config: Annotated[Configuracao, Depends(obter_configuracao)],
) -> None:
    if not config.teste_pipeline_habilitado:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Rotas de teste só existem com AMBIENTE=local (inferido automaticamente).",
        )

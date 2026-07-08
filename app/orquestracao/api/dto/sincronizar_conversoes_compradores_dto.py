from __future__ import annotations

from pydantic import BaseModel, Field


class RespostaSincronizarConversoesCompradores(BaseModel):
    avaliados: int = Field(description="Elegíveis ainda não convertidos.")
    convertidos: int = Field(
        description="Marcados como convertidos nesta execução (usuario_comprador.n_acessos > 1)."
    )

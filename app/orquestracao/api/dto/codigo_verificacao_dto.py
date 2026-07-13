from __future__ import annotations

from pydantic import BaseModel, Field


class PedidoSmsCodigoVerificacao(BaseModel):
    telefone: str = Field(..., min_length=5, max_length=500)
    codigo: str = Field(..., min_length=1, max_length=32)


class RespostaSmsCodigoVerificacao(BaseModel):
    id_externo: str
    id_provedor: str
    status_ultimo: str = "processando"

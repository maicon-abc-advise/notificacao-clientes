from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class PedidoEmailFornecedorContato(BaseModel):
    consulta_id: UUID | None = None
    cnpj_basico: str = Field(..., min_length=8, max_length=8)
    mensagem: str = Field(..., min_length=1, max_length=8000)
    nome: str = Field(..., min_length=1, max_length=256)
    email: str | None = Field(default=None, max_length=320)


class RespostaEmailFornecedorContato(BaseModel):
    id_externo: str
    id_provedor: str
    tipo_template: str
    destinatario: str
    status_ultimo: str = "processando"
    idempotente: bool = False

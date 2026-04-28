from __future__ import annotations
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field

class VerificarCreditosCorpo(BaseModel):
    usuario_id: UUID
    email_destinatario: EmailStr
    creditos_restantes: int = Field(..., ge=0)
    limiar_creditos_no_fim: int = Field(
        default=5,
        ge=0,
        description="Se restantes > 0 e <= limiar, dispara CREDITOS_NO_FIM.",
    )
    nome_fantasia: str | None = Field(default=None, max_length=256)
    link_area_creditos: str = Field(default="https://buscafornecedor.com.br/creditos")

class RespostaVerificarCreditos(BaseModel):
    acao: str = Field(description="email_enfileirado | nada")
    tipo_template: str | None = None
    external_id: str | None = None
    motivo: str = ""

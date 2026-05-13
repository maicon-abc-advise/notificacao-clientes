from __future__ import annotations

from pydantic import BaseModel, Field


class CorpoConfirmacaoSenha(BaseModel):
    senha: str = Field(min_length=1)

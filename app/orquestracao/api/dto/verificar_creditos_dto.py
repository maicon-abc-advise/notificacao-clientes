from __future__ import annotations

from pydantic import BaseModel, Field


class RespostaVerificarCreditos(BaseModel):
    avaliados: int = Field(description="Fornecedores no limiar ou com créditos zerados (consulta ao banco).")
    enfileirados: int = Field(description="E-mails de alerta colocados na fila com sucesso.")
    ignorados: int = Field(description="Sem envio (preferências, cadência 7d, fila ocupada, etc.).")

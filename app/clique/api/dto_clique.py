"""Resposta JSON do GET /v1/clique/{token} (consumo pelo front Lovable)."""

from pydantic import BaseModel, Field


class DadosCliqueResposta(BaseModel):
    uf: str = Field(default="", description="UF do contexto do envio.")
    segmento: str = Field(default="", description="Segmento do contexto do envio.")
    nome_empresa: str = Field(
        default="Sua empresa",
        description="nome_fantasia do engajamento ou fallback.",
    )

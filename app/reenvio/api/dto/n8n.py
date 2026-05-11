from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PedidoClaimN8N(BaseModel):
    limite: int = Field(default=100, ge=1, le=500)


class PedidoConfirmarConsumoN8N(BaseModel):
    id_externo: str = Field(..., min_length=1, max_length=128)


class ItemPendenteN8N(BaseModel):
    canal: str = Field(description="email | sms")
    id_externo: str
    destinatario: str
    tipo_template: str
    contexto: dict[str, str] = Field(default_factory=dict)
    remetente: str | None = None
    fornecedor_id: str | None = None
    cnpj_basico: str | None = None
    consulta_id: str | None = None
    origem: str
    criado_em: str | None = None
    payload_envio: dict[str, Any] = Field(
        default_factory=dict,
        description="Payload pronto para POST /v1/mensagens/email ou /v1/mensagens/sms.",
    )


class RespostaItensPendentesN8N(BaseModel):
    total: int
    itens: list[ItemPendenteN8N] = Field(default_factory=list)


class RespostaClaimN8N(RespostaItensPendentesN8N):
    ttl_claim_segundos: int


class RespostaConfirmarConsumoN8N(BaseModel):
    id_externo: str
    status: str = Field(description="removido | ja_nao_existia")

from enum import StrEnum
from typing import Any
from pydantic import BaseModel, Field

class CanalMensagem(StrEnum):
    EMAIL = "email"
    SMS = "sms"

# Pedido de envio de email
class PedidoEnvioEmail(BaseModel):
    destinatario: str = Field(..., min_length=3, description="E-mail do destinatário (campo to na API do provedor)")
    assunto: str = Field(..., min_length=1)
    corpo_html: str = Field(
        ...,
        min_length=1,
        description="Conteúdo HTML do e-mail (Zenvia: conteúdo type email, campo html).",
    )
    remetente: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description="ID do remetente (from); se omitido, usa ZENVIA_EMAIL_FROM no servidor.",
    )
    id_externo: str | None = Field(default=None, max_length=64, description="Mapeia para externalId se informado.")

# Pedido de envio de sms
class PedidoEnvioSms(BaseModel):
    destinatario: str = Field(
        ...,
        min_length=5,
        max_length=20,
        description="Destinatário no formato exigido pelo provedor (ex. E.164, sem espaços).",
    )
    texto: str = Field(..., min_length=1, description="Corpo do SMS (texto curto).")
    remetente: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description="ID do remetente; se omitido, usa ZENVIA_SMS_FROM no servidor.",
    )
    id_externo: str | None = Field(default=None, max_length=64)

# Resultado do envio de mensagem
class ResultadoEnvioMensagem(BaseModel):
    id_provedor: str
    canal: CanalMensagem
    resposta_parcial: dict[str, Any] = Field(
        default_factory=dict,
        description="Trecho da resposta JSON (útil para suporte; pode vazio em testes).",
    )

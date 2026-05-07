from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

CodigoStatusMensagem = Literal["REJECTED", "SENT", "DELIVERED", "NOT_DELIVERED", "READ", "CLICK"]
TipoEventoWebhook = Literal["MESSAGE_STATUS"]
CanalWebhook = Literal["email", "sms"]

# Corpo do evento MESSAGE_STATUS da Zenvia
class CorpoMessageStatusZenvia(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timestamp: str = Field(..., min_length=1)
    code: CodigoStatusMensagem
    description: str | None = None
    cause: str | None = None

# Webhook do evento MESSAGE_STATUS da Zenvia
class WebhookMessageStatusZenvia(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Id único do evento (idempotência).
    id: str = Field(..., min_length=1, description="Id único do evento (idempotência).")
    # Timestamp do evento.
    timestamp: str = Field(..., min_length=1)
    # Tipo de evento.
    type: TipoEventoWebhook
    # Id da subscrição.
    subscriptionId: str = Field(..., min_length=1)
    # Canal do evento.
    channel: CanalWebhook
    # Id da mensagem.
    messageId: str = Field(..., min_length=1)
    # Índice do conteúdo.
    contentIndex: int = Field(default=0, ge=0)
    messageStatus: CorpoMessageStatusZenvia
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TipoEventoWebhook = Literal["MESSAGE_STATUS"]


class ZenviaWebhookCausa(BaseModel):
    model_config = ConfigDict(extra="ignore")

    channelErrorCode: str | None = None
    reason: str | None = None
    details: str | None = None


class ZenviaContextButton(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: str | None = None
    payload: str | None = None


class ZenviaContextoWebhook(BaseModel):
    model_config = ConfigDict(extra="ignore")

    button: ZenviaContextButton | None = None


class ZenviaEmailClientInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    machineOpen: bool | None = None
    userAgent: str | None = None
    sourceIp: str | None = None
    url: str | None = None


class ZenviaChannelDataEmail(BaseModel):
    model_config = ConfigDict(extra="ignore")

    clientInfo: ZenviaEmailClientInfo | None = None


class ZenviaChannelDataSms(BaseModel):
    model_config = ConfigDict(extra="ignore")

    carrier: str | None = None


class ZenviaChannelDataRcs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    realChannel: str | None = None


class ZenviaChannelDataWebhook(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sms: ZenviaChannelDataSms | None = None
    rcs: ZenviaChannelDataRcs | None = None
    email: ZenviaChannelDataEmail | None = None


class MensagemWebhookZenvia(BaseModel):
    """Bloco ``message`` do webhook MESSAGE_STATUS (Zenvia)."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str | None = Field(default=None, min_length=1)
    externalId: str | None = None
    contentIndex: int | None = Field(default=None, ge=0)
    from_: str | None = Field(default=None, validation_alias="from")
    to: str | None = None


class CorpoMessageStatusZenvia(BaseModel):
    model_config = ConfigDict(extra="ignore")

    timestamp: str = Field(..., min_length=1)
    channel: str | None = None
    code: str = Field(..., min_length=1, description="Status Zenvia (ex.: SENT, DELIVERED); aceita códigos novos.")
    description: str | None = None
    causes: list[ZenviaWebhookCausa] = Field(default_factory=list)
    context: ZenviaContextoWebhook | None = None
    channelData: ZenviaChannelDataWebhook | None = None


class WebhookMessageStatusZenvia(BaseModel):
    """Payload MESSAGE_STATUS conforme contrato Zenvia (inglês, camelCase)."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(..., min_length=1, description="Id único do evento (idempotência).")
    timestamp: str = Field(..., min_length=1)
    subscriptionId: str = Field(..., min_length=1)
    type: TipoEventoWebhook
    channel: str = Field(..., min_length=1)
    messageId: str | None = Field(default=None, description="Obsoleto na doc; mantido opcional.")
    contentIndex: int | None = Field(default=None, ge=0, description="Obsoleto na doc; mantido opcional.")
    message: MensagemWebhookZenvia | None = None
    messageStatus: CorpoMessageStatusZenvia

    def obter_id_mensagem_zenvia(self) -> str | None:
        if self.message is not None:
            mid = (self.message.id or "").strip()
            if mid:
                return mid
        root = (self.messageId or "").strip()
        return root or None

    def texto_para_classificacao_falha(self) -> str | None:
        """Texto único para heurísticas (cause/description + itens de ``causes``)."""
        parts: list[str] = []
        if self.messageStatus.description:
            parts.append(self.messageStatus.description)
        for c in self.messageStatus.causes:
            for x in (c.channelErrorCode, c.reason, c.details):
                if x:
                    parts.append(x)
        s = " ".join(parts).strip()
        return s or None

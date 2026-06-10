from pydantic import BaseModel, Field


class ClienteLigacao(BaseModel):
    number: str = Field(..., description="Telefone E.164, ex.: +5511999999999")


class VariaveisAssistente(BaseModel):
    cnpj_basico: str
    numeroDeBuscas: str
    ufBuscada: str
    segmentoBuscado: str


class SobrescritasAssistente(BaseModel):
    variableValues: VariaveisAssistente


class MetadadosLigacao(BaseModel):
    id_externo: str


class PedidoDisparoLigacao(BaseModel):
    customer: ClienteLigacao
    assistantOverrides: SobrescritasAssistente
    metadata: MetadadosLigacao

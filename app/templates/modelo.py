from dataclasses import dataclass
from enum import StrEnum

class CodigoTipoTemplate(StrEnum):
    APARECEU_BUSCA = "APARECEU_BUSCA"
    APARECEU_BUSCA_SEM_REGISTRO = "APARECEU_BUSCA_SEM_REGISTRO"
    CREDITOS_NO_FIM = "CREDITOS_NO_FIM"
    LEMBRETE_CREDITOS_ESGOTADOS = "LEMBRETE_CREDITOS_ESGOTADOS"
    CONSULTADO_SEM_EMAIL = "CONSULTADO_SEM_EMAIL"
    APRESENTACAO = "APRESENTACAO"

@dataclass(frozen=True, slots=True)
class TemplateNotificacao:
    id: str
    tipo: str
    email: str | None
    sms: str

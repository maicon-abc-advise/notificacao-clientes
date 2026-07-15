from dataclasses import dataclass
from enum import StrEnum

class CodigoTipoTemplate(StrEnum):
    APARECEU_BUSCA = "APARECEU_BUSCA"
    APARECEU_BUSCA_SEM_REGISTRO = "APARECEU_BUSCA_SEM_REGISTRO"
    CREDITOS_NO_FIM = "CREDITOS_NO_FIM"
    LEMBRETE_CREDITOS_ESGOTADOS = "LEMBRETE_CREDITOS_ESGOTADOS"
    CONSULTADO_SEM_EMAIL = "CONSULTADO_SEM_EMAIL"
    APRESENTACAO = "APRESENTACAO"
    BUSCA_COMPRADOR = "BUSCA_COMPRADOR"
    CODIGO_VERIFICACAO = "CODIGO_VERIFICACAO"
    CONTATO_FORNECEDOR_SEM_CADASTRO = "CONTATO_FORNECEDOR_SEM_CADASTRO"
    CONTATO_FORNECEDOR_CADASTRADO = "CONTATO_FORNECEDOR_CADASTRADO"

@dataclass(frozen=True, slots=True)
class TemplateNotificacao:
    id: str
    tipo: str
    email: str | None
    sms: str
    variante: str = "simples"
    assunto: str | None = None

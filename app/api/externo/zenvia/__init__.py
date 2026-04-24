"""Integração HTTP com a API de mensageria Zenvia (v2)."""

from app.api.externo.zenvia.adaptador_envio import AdaptadorEnvioZenvia
from app.excecoes.erro import ErroEnvioZenvia
from app.api.externo.zenvia.parametros import ParametrosZenvia, obter_parametros_zenvia

__all__ = [
    "AdaptadorEnvioZenvia",
    "ErroEnvioZenvia",
    "ParametrosZenvia",
    "obter_parametros_zenvia",
]

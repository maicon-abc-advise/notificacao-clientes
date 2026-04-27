"""Integração HTTP com a API de mensageria Zenvia (v2)."""

from app.mensageria.api.externo.zenvia.adaptador_envio import AdaptadorEnvioZenvia
from app.mensageria.excecoes.erro import ErroEnvioZenvia
from app.mensageria.api.externo.zenvia.parametros import ParametrosZenvia, obter_parametros_zenvia

__all__ = [
    "AdaptadorEnvioZenvia",
    "ErroEnvioZenvia",
    "ParametrosZenvia",
    "obter_parametros_zenvia",
]

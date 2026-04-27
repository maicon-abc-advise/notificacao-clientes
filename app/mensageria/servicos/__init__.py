"""Portas e modelos de envio (sem acoplamento a provedor específico)."""

from app.mensageria.api.dto.modelos import (
    PedidoEnvioEmail,
    PedidoEnvioSms,
    ResultadoEnvioMensagem,
)
from app.mensageria.servicos.porta import PortaEnvioMensagem

__all__ = [
    "PedidoEnvioEmail",
    "PedidoEnvioSms",
    "PortaEnvioMensagem",
    "ResultadoEnvioMensagem",
]

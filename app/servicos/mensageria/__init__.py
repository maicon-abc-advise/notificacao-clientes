"""Portas e modelos de envio (sem acoplamento a provedor específico)."""

from app.api.dto.modelos import (
    PedidoEnvioEmail,
    PedidoEnvioSms,
    ResultadoEnvioMensagem,
)
from app.servicos.mensageria.porta import PortaEnvioMensagem

__all__ = [
    "PedidoEnvioEmail",
    "PedidoEnvioSms",
    "PortaEnvioMensagem",
    "ResultadoEnvioMensagem",
]

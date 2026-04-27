"""Portas e modelos de envio (sem acoplamento a provedor específico)."""

from app.mensageria.api.dto.modelos import (
    PedidoEmailProvedor,
    PedidoEnvioEmail,
    PedidoEnvioSms,
    PedidoSmsProvedor,
    ResultadoEnvioMensagem,
)
from app.mensageria.servicos.porta import PortaEnvioMensagem

__all__ = [
    "PedidoEmailProvedor",
    "PedidoEnvioEmail",
    "PedidoEnvioSms",
    "PedidoSmsProvedor",
    "PortaEnvioMensagem",
    "ResultadoEnvioMensagem",
]

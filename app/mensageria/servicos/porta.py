from typing import Protocol, runtime_checkable
from app.mensageria.api.dto.modelos import (
    PedidoEmailProvedor,
    PedidoSmsProvedor,
    ResultadoEnvioMensagem,
)

@runtime_checkable
class ProvedorCanalEmail(Protocol):
    def enviar_email(self, pedido: PedidoEmailProvedor) -> ResultadoEnvioMensagem: ...


@runtime_checkable
class ProvedorCanalSms(Protocol):
    def enviar_sms(self, pedido: PedidoSmsProvedor) -> ResultadoEnvioMensagem: ...

@runtime_checkable
class PortaEnvioMensagem(Protocol):
    def enviar_email(self, pedido: PedidoEmailProvedor) -> ResultadoEnvioMensagem: ...
    def enviar_sms(self, pedido: PedidoSmsProvedor) -> ResultadoEnvioMensagem: ...
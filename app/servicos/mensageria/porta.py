from typing import Protocol, runtime_checkable
from app.api.dto.modelos import PedidoEnvioEmail, PedidoEnvioSms, ResultadoEnvioMensagem

@runtime_checkable
class ProvedorCanalEmail(Protocol):
    def enviar_email(self, pedido: PedidoEnvioEmail) -> ResultadoEnvioMensagem: ...

@runtime_checkable
class ProvedorCanalSms(Protocol):
    def enviar_sms(self, pedido: PedidoEnvioSms) -> ResultadoEnvioMensagem: ...

@runtime_checkable
class PortaEnvioMensagem(Protocol):
    def enviar_email(self, pedido: PedidoEnvioEmail) -> ResultadoEnvioMensagem: ...
    def enviar_sms(self, pedido: PedidoEnvioSms) -> ResultadoEnvioMensagem: ...
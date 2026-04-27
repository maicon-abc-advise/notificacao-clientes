from app.mensageria.api.dto.modelos import (
    PedidoEmailProvedor,
    PedidoSmsProvedor,
    ResultadoEnvioMensagem,
)
from app.mensageria.servicos.porta import PortaEnvioMensagem, ProvedorCanalEmail, ProvedorCanalSms


class PortaMensagemComposta(PortaEnvioMensagem):

    def __init__(
        self,
        provedor_email: ProvedorCanalEmail,
        provedor_sms: ProvedorCanalSms,
    ) -> None:
        self._email = provedor_email
        self._sms = provedor_sms

    def enviar_email(self, pedido: PedidoEmailProvedor) -> ResultadoEnvioMensagem:
        return self._email.enviar_email(pedido)

    def enviar_sms(self, pedido: PedidoSmsProvedor) -> ResultadoEnvioMensagem:
        return self._sms.enviar_sms(pedido)

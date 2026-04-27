from app.mensageria.api.dto.modelos import PedidoEnvioEmail, PedidoEnvioSms, ResultadoEnvioMensagem
from app.mensageria.servicos.porta import PortaEnvioMensagem, ProvedorCanalEmail, ProvedorCanalSms

class PortaMensagemComposta(PortaEnvioMensagem):

    def __init__(
        self,
        provedor_email: ProvedorCanalEmail,
        provedor_sms: ProvedorCanalSms,
    ) -> None:
        # inicializa os provedores de email e sms
        self._email = provedor_email
        self._sms = provedor_sms

    # envia o email
    def enviar_email(self, pedido: PedidoEnvioEmail) -> ResultadoEnvioMensagem:
        return self._email.enviar_email(pedido)

    # envia o sms
    def enviar_sms(self, pedido: PedidoEnvioSms) -> ResultadoEnvioMensagem:
        return self._sms.enviar_sms(pedido)

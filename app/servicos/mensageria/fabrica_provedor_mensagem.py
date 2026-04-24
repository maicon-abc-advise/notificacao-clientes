from app.api.externo.zenvia.adaptador_envio import AdaptadorEnvioZenvia
from app.api.externo.zenvia.parametros import obter_parametros_zenvia
from app.excecoes.erro_provedor import FalhaConfiguracaoProvedor
from app.servicos.mensageria.porta import PortaEnvioMensagem, ProvedorCanalEmail, ProvedorCanalSms
from app.servicos.mensageria.porta_composta import PortaMensagemComposta
from app.config.config import Configuracao
from app.config.provedor_mensagens import ProvedorMensagem

def _zenvia_com_token() -> AdaptadorEnvioZenvia:
    pz = obter_parametros_zenvia()
    if not pz.api_token:
        raise FalhaConfiguracaoProvedor(
            "Conector zenvia: defina ZENVIA_API_TOKEN no ambiente.",
            status_code=503,
        )
    return AdaptadorEnvioZenvia(pz)

def _criar_provedor_email(tipo: ProvedorMensagem) -> ProvedorCanalEmail:
    if tipo == ProvedorMensagem.ZENVIA:
        return _zenvia_com_token()
    raise FalhaConfiguracaoProvedor(
        f"Provedor de e-mail não suportado: {tipo!s}. Ajuste MENSAGENS_PROVEDOR_EMAIL.",
        status_code=501,
    )

def _criar_provedor_sms(tipo: ProvedorMensagem) -> ProvedorCanalSms:
    if tipo == ProvedorMensagem.ZENVIA:
        return _zenvia_com_token()
    raise FalhaConfiguracaoProvedor(
        f"Provedor de SMS não suportado: {tipo!s}. Ajuste MENSAGENS_PROVEDOR_SMS.",
        status_code=501,
    )

def construir_porta_mensagem(config: Configuracao) -> PortaEnvioMensagem:
    pe, ps = config.mensagens_provedor_email, config.mensagens_provedor_sms
    if pe == ps and pe == ProvedorMensagem.ZENVIA:
        return _zenvia_com_token()
    instancia_email = _criar_provedor_email(pe)
    instancia_sms = _criar_provedor_sms(ps)
    if instancia_email is instancia_sms:
        return instancia_email  
    return PortaMensagemComposta(instancia_email, instancia_sms)

import json
from typing import Any
import httpx
from app.mensageria.api.dto.modelos import (
    CanalMensagem,
    PedidoEnvioEmail,
    PedidoEnvioSms,
    ResultadoEnvioMensagem,
)
from app.mensageria.excecoes.erro import ErroEnvioZenvia
from app.mensageria.api.externo.zenvia.parametros import ParametrosZenvia

_CABECALHO_TOKEN = "X-API-TOKEN"
_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_PATH_EMAIL = "/v2/channels/email/messages"
_PATH_SMS = "/v2/channels/sms/messages"

class AdaptadorEnvioZenvia:

    def __init__(self, parametros: ParametrosZenvia, cliente: httpx.Client | None = None) -> None:
        self._parametros = parametros
        if cliente is not None:
            self._cliente = cliente
        else:
            if not self._parametros.api_token:
                msg = "ZENVIA_API_TOKEN não configurado."
                raise ValueError(msg)
            self._cliente = self._criar_cliente()

    # cria o cliente para usar a API do Zenvia caso não tenha sido passado.
    def _criar_cliente(self) -> httpx.Client:
        base = str(self._parametros.api_base_url).rstrip("/")
        return httpx.Client(
            base_url=base,
            headers={_CABECALHO_TOKEN: self._parametros.api_token or ""},
            timeout=_TIMEOUT,
        )

    # extrai o id da resposta
    def _extrair_id(self, dados: dict[str, Any]) -> str:
        return str(dados.get("id") or "")

    def _falha(self, r: httpx.Response) -> None:
        corpo = r.text[:2000] if r.text else None
        try:
            msg = f"Zenvia HTTP {r.status_code}"
            if corpo:
                msg = f"{msg}: {corpo}"
        except Exception:
            msg = f"Zenvia HTTP {r.status_code}"
        raise ErroEnvioZenvia(msg, status_code=r.status_code, corpo=corpo)

    def enviar_email(self, pedido: PedidoEnvioEmail) -> ResultadoEnvioMensagem:

        # extrai o remetente do pedido ou usa o remetente padrão
        remetente = pedido.remetente or self._parametros.email_remetente_padrao

        if not remetente:
            raise ValueError("Remetente de e-mail: informe no pedido ou configure ZENVIA_EMAIL_FROM no servidor.")
        conteudo: dict[str, Any] = {
            "type": "email",
            "subject": pedido.assunto,
        }
        # se o corpo html foi informado, adiciona ao conteudo
        if pedido.corpo_html:
            conteudo["html"] = pedido.corpo_html

        # cria o corpo da requisição
        corpo_req: dict[str, Any] = {
            "from": remetente,
            "to": pedido.destinatario,
            "contents": [conteudo],
        }

        # se o id externo foi informado, adiciona ao corpo da requisição
        if pedido.id_externo:
            corpo_req["externalId"] = pedido.id_externo

        # envia a requisição
        r = self._cliente.post(_PATH_EMAIL, json=corpo_req)
        if r.is_error:
            self._falha(r)
        try:
            # extrai os dados da resposta
            dados = r.json()
        except json.JSONDecodeError as e:
            raise ErroEnvioZenvia("Resposta Zenvia não é JSON", status_code=r.status_code) from e
        id_ = self._extrair_id(dados)
        if not id_:
            id_ = "(sem id na resposta)"

        # cria o resultado do envio de mensagem
        return ResultadoEnvioMensagem(
            id_provedor=id_,
            canal=CanalMensagem.EMAIL,
            resposta_parcial={k: dados[k] for k in ("id", "from", "to", "channel", "externalId") if k in dados},
        )

    def enviar_sms(self, pedido: PedidoEnvioSms) -> ResultadoEnvioMensagem:

        remetente = pedido.remetente or self._parametros.sms_remetente_padrao
        if not remetente:
            raise ValueError("Remetente SMS: informe no pedido ou configure ZENVIA_SMS_FROM no servidor.")
        corpo_req: dict[str, Any] = {
            "from": remetente,
            "to": pedido.destinatario,
            "contents": [{"type": "text", "text": pedido.texto}],
        }

        if pedido.id_externo:
            corpo_req["externalId"] = pedido.id_externo

        r = self._cliente.post(_PATH_SMS, json=corpo_req)

        if r.is_error:
            self._falha(r)

        try:
            dados = r.json()
        except json.JSONDecodeError as e:
            raise ErroEnvioZenvia("Resposta Zenvia não é JSON", status_code=r.status_code) from e
        id_ = self._extrair_id(dados)

        if not id_:
            id_ = "(sem id na resposta)"
            
        return ResultadoEnvioMensagem(
            id_provedor=id_,
            canal=CanalMensagem.SMS,
            resposta_parcial={k: dados[k] for k in ("id", "from", "to", "channel", "externalId") if k in dados},
        )

    def fechar(self) -> None:
        if not self._cliente.is_closed:
            self._cliente.close()

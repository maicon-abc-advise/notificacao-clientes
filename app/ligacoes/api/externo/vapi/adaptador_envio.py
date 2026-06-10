from typing import Any

import httpx

from app.ligacoes.api.dto.modelos import PedidoDisparoLigacao

_VAPI_URL = "https://api.vapi.ai/call"
_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class ErroEnvioVapi(Exception):
    def __init__(self, mensagem: str, *, status_code: int | None = None, corpo: str | None = None) -> None:
        super().__init__(mensagem)
        self.status_code = status_code
        self.corpo = corpo


def montar_corpo_vapi(
    pedido: PedidoDisparoLigacao,
    *,
    assistant_id: str,
    phone_number_id: str,
) -> dict[str, Any]:
    return {
        "assistantId": assistant_id,
        "phoneNumberId": phone_number_id,
        "customer": {"number": pedido.customer.number.strip()},
        "assistantOverrides": {
            "variableValues": pedido.assistantOverrides.variableValues.model_dump(),
        },
        "metadata": pedido.metadata.model_dump(),
    }


async def disparar_ligacao_vapi(
    pedido: PedidoDisparoLigacao,
    *,
    api_key: str,
    assistant_id: str,
    phone_number_id: str,
) -> dict[str, Any]:
    if not api_key:
        raise ValueError("VAPI_API_KEY não configurado.")
    if not assistant_id:
        raise ValueError("VAPI_ASSISTANT_ID não configurado.")
    if not phone_number_id:
        raise ValueError("VAPI_PHONE_NUMBER_ID não configurado.")

    corpo = montar_corpo_vapi(
        pedido,
        assistant_id=assistant_id,
        phone_number_id=phone_number_id,
    )
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=_TIMEOUT) as cliente:
        resposta = await cliente.post(_VAPI_URL, json=corpo, headers=headers)

    if resposta.is_error:
        texto = (resposta.text or "")[:2000]
        raise ErroEnvioVapi(
            f"Vapi HTTP {resposta.status_code}: {texto}",
            status_code=resposta.status_code,
            corpo=texto,
        )

    try:
        return resposta.json()
    except Exception as e:
        raise ErroEnvioVapi(
            "Resposta Vapi não é JSON",
            status_code=resposta.status_code,
            corpo=resposta.text[:2000] if resposta.text else None,
        ) from e

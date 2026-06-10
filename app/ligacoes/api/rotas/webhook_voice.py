import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.config.config import Configuracao, obter_configuracao
from app.ligacoes.servicos.process_voice_webhook import processar_webhook_voz
from app.orquestracao.api.dependencias import PoolOrquestracao

_log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/webhooks/vapi",
    tags=["ligações — webhook"],
)


def _validar_secret(config: Configuracao, secret_header: str | None) -> None:
    esperado = (config.vapi_webhook_secret or "").strip()
    if not esperado:
        return
    recebido = (secret_header or "").strip()
    if recebido != esperado:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="webhook secret inválido")


@router.post("/voice", status_code=status.HTTP_200_OK)
async def post_webhook_vapi_voice(
    request: Request,
    pool: PoolOrquestracao,
    config: Annotated[Configuracao, Depends(obter_configuracao)],
    x_vapi_secret: Annotated[str | None, Header(alias="X-Vapi-Secret")] = None,
) -> dict[str, Any]:
    _validar_secret(config, x_vapi_secret)
    bruto = await request.body()
    if not bruto:
        return {"ok": True, "ignorado": "corpo_vazio"}
    try:
        payload = json.loads(bruto)
    except json.JSONDecodeError:
        _log.warning("Webhook Vapi voice: JSON inválido")
        return {"ok": True, "ignorado": "json_invalido"}
    if not isinstance(payload, dict):
        return {"ok": True, "ignorado": "payload_invalido"}
    return await processar_webhook_voz(pool, payload)

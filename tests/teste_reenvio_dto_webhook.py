import pytest
from pydantic import ValidationError

from app.reenvio.api.dto.webhook_zenvia import WebhookMessageStatusZenvia


def _payload_valido_v2(*, channel: str = "email", code: str = "READ") -> dict:
    return {
        "id": "evt-1",
        "timestamp": "2019-08-24T14:15:22Z",
        "subscriptionId": "sub-1",
        "type": "MESSAGE_STATUS",
        "channel": channel,
        "messageId": "msg-root-legacy",
        "contentIndex": 0,
        "message": {
            "id": "msg-1",
            "externalId": "ext-1",
            "contentIndex": 0,
            "from": "email@email.com",
            "to": "received_email@email.com",
        },
        "messageStatus": {
            "timestamp": "2019-08-24T14:15:22Z",
            "channel": channel,
            "code": code,
            "description": "ok",
            "causes": [
                {
                    "channelErrorCode": "x",
                    "reason": "y",
                    "details": "z",
                }
            ],
            "context": {"button": {"type": "text", "payload": "p"}},
            "channelData": {
                "email": {
                    "clientInfo": {
                        "machineOpen": True,
                        "userAgent": "Mozilla/5.0",
                        "sourceIp": "255.255.255.255",
                        "url": "https://example.com/clicked-link",
                    }
                }
            },
        },
    }


def test_webhook_message_status_ok() -> None:
    m = WebhookMessageStatusZenvia.model_validate(_payload_valido_v2())
    assert m.messageStatus.code == "READ"
    assert m.obter_id_mensagem_zenvia() == "msg-1"


def test_webhook_prefere_message_id_sobre_message_id_raiz() -> None:
    p = _payload_valido_v2()
    p["message"]["id"] = "from-message"
    p["messageId"] = "from-root"
    m = WebhookMessageStatusZenvia.model_validate(p)
    assert m.obter_id_mensagem_zenvia() == "from-message"


def test_webhook_fallback_message_id_raiz_sem_message() -> None:
    p = _payload_valido_v2()
    del p["message"]
    m = WebhookMessageStatusZenvia.model_validate(p)
    assert m.obter_id_mensagem_zenvia() == "msg-root-legacy"


def test_webhook_clicked_ok() -> None:
    p = _payload_valido_v2(code="CLICKED")
    p["messageStatus"]["causes"] = []
    m = WebhookMessageStatusZenvia.model_validate(p)
    assert m.messageStatus.code == "CLICKED"


def test_webhook_texto_classificacao_inclui_causes() -> None:
    m = WebhookMessageStatusZenvia.model_validate(_payload_valido_v2())
    t = m.texto_para_classificacao_falha()
    assert t is not None
    assert "ok" in t
    assert "x" in t and "y" in t and "z" in t


def test_webhook_campos_extra_na_raiz_sao_ignorados() -> None:
    p = _payload_valido_v2()
    p["futuroCampoZenvia"] = "ignored"
    m = WebhookMessageStatusZenvia.model_validate(p)
    assert m.id == "evt-1"


def test_webhook_abertura_por_maquina() -> None:
    p = _payload_valido_v2()
    p["messageStatus"]["channelData"]["email"]["clientInfo"]["machineOpen"] = True
    m = WebhookMessageStatusZenvia.model_validate(p)
    assert m.abertura_por_maquina() is True

    p["messageStatus"]["channelData"]["email"]["clientInfo"]["machineOpen"] = False
    m = WebhookMessageStatusZenvia.model_validate(p)
    assert m.abertura_por_maquina() is False


def test_webhook_rejeita_type_invalido() -> None:
    p = _payload_valido_v2()
    p["type"] = "OTHER"
    with pytest.raises(ValidationError):
        WebhookMessageStatusZenvia.model_validate(p)


def test_webhook_aceita_code_desconhecido() -> None:
    m = WebhookMessageStatusZenvia.model_validate(_payload_valido_v2(code="NOVO_STATUS_ZENVIA"))
    assert m.messageStatus.code == "NOVO_STATUS_ZENVIA"

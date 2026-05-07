import pytest
from pydantic import ValidationError

from app.reenvio.api.dto.webhook_zenvia import WebhookMessageStatusZenvia


def _payload_valido() -> dict:
    return {
        "id": "evt-1",
        "timestamp": "2026-04-27T12:00:00Z",
        "type": "MESSAGE_STATUS",
        "subscriptionId": "sub-1",
        "channel": "email",
        "messageId": "msg-1",
        "contentIndex": 0,
        "messageStatus": {
            "timestamp": "2026-04-27T12:00:01Z",
            "code": "READ",
            "description": "read",
            "cause": None,
        },
    }


def test_webhook_message_status_ok() -> None:
    m = WebhookMessageStatusZenvia.model_validate(_payload_valido())
    assert m.messageStatus.code == "READ"


def test_webhook_message_status_click_ok() -> None:
    p = _payload_valido()
    p["messageStatus"] = {
        "timestamp": "2026-04-27T12:00:01Z",
        "code": "CLICK",
        "description": "click",
        "cause": None,
    }
    m = WebhookMessageStatusZenvia.model_validate(p)
    assert m.messageStatus.code == "CLICK"


def test_webhook_rejeita_campo_extra() -> None:
    p = _payload_valido()
    p["extra"] = "nope"
    with pytest.raises(ValidationError):
        WebhookMessageStatusZenvia.model_validate(p)

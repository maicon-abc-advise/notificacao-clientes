import asyncio

import pytest

from app.mensageria.api.dto.modelos import CanalMensagem
from app.mensageria.servicos import fallback_sms_invalido as fb
from app.reenvio.servicos.validacao_telefone_sms_br import MOTIVO_FALHA_SMS_TELEFONE_INVALIDO


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        self.store[key] = value


def test_redis_idempotencia_replay_igual() -> None:
    r = _FakeRedis()

    async def _run() -> None:
        await fb.gravar_idempotencia_fallback(
            r,
            "ext-orig",
            canal_efetivo="email",
            id_externo_novo="ext-orig:fallback_email:abc",
        )
        replay = await fb.ler_replay_idempotencia(r, "ext-orig")
        assert replay is not None
        assert replay.canal == CanalMensagem.EMAIL
        assert replay.id_provedor == fb.ID_PROVEDOR_REENFILEIRADO
        assert replay.resposta_parcial["idempotente"] is True
        assert replay.resposta_parcial["id_externo_novo"] == "ext-orig:fallback_email:abc"
        assert replay.resposta_parcial["motivo"] == MOTIVO_FALHA_SMS_TELEFONE_INVALIDO

    asyncio.run(_run())


def test_resultado_sem_flag_idempotente() -> None:
    out = fb.resultado_reenfileirado(
        canal_efetivo="sms",
        id_externo_pedido_original="x",
        id_externo_novo="y",
    )
    assert out.resposta_parcial.get("idempotente") is None

"""Envio simulado (sem HTTP) quando ``USE_ZENVIA_MOCK=true``."""

from __future__ import annotations

import uuid

from app.mensageria.api.dto.modelos import (
    CanalMensagem,
    PedidoEmailProvedor,
    PedidoSmsProvedor,
    ResultadoEnvioMensagem,
)


class AdaptadorZenviaMock:
    def enviar_email(self, pedido: PedidoEmailProvedor) -> ResultadoEnvioMensagem:
        return ResultadoEnvioMensagem(
            id_provedor=f"mock-zenvia-email-{uuid.uuid4().hex[:16]}",
            canal=CanalMensagem.EMAIL,
            resposta_parcial={"mock": True, "destinatario": pedido.destinatario},
        )

    def enviar_sms(self, pedido: PedidoSmsProvedor) -> ResultadoEnvioMensagem:
        return ResultadoEnvioMensagem(
            id_provedor=f"mock-zenvia-sms-{uuid.uuid4().hex[:16]}",
            canal=CanalMensagem.SMS,
            resposta_parcial={"mock": True, "destinatario": pedido.destinatario},
        )

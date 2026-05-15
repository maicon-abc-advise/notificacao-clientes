import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.mensageria.api.dto.modelos import CanalMensagem, PedidoEnvioSms
from app.mensageria.servicos import fallback_sms_invalido as fb
from app.orquestracao.repositorios.engajamento_consulta_repo import SnapshotEngajamentoOrquestracao
from app.reenvio.repositorios.redis_consulta_notificacao import fase_pendente_sms
from app.reenvio.servicos.engajamento_estado import EngajamentoCanalAgregado
from app.reenvio.servicos.validacao_telefone_sms_br import MOTIVO_FALHA_SMS_TELEFONE_INVALIDO
from app.templates.modelo import CodigoTipoTemplate


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


def test_fallback_libera_trava_pendente_sms_antes_de_reenfileirar() -> None:
    """Evita ConsultaJaNotificadaError: trava ainda é ``pendente-sms:id`` do item da fila."""
    consulta_id = uuid.uuid4()
    cnpj8 = "12345678"
    snap = SnapshotEngajamentoOrquestracao(
        engajamento_email=EngajamentoCanalAgregado.INATIVO.value,
        engajamento_sms=EngajamentoCanalAgregado.ATIVO.value,
        contatos_email=[],
        contatos_sms=[
            {"endereco": "5515000", "estado": "ativo", "ultima_atualizacao_em": ""},
            {"endereco": "5511987654321", "estado": "ativo", "ultima_atualizacao_em": ""},
        ],
        ultimo_envio_email_endereco=None,
        ultimo_envio_sms_endereco=None,
        ultimo_lembrete_limite_semanal_em=None,
    )
    pedido = PedidoEnvioSms(
        destinatario="5515000",
        tipo_template=CodigoTipoTemplate.APARECEU_BUSCA,
        contexto={},
        remetente=None,
        id_externo="ext-fila-1",
        fornecedor_id=None,
        cnpj_basico=cnpj8,
        consulta_id=consulta_id,
    )

    async def _run() -> None:
        redis = MagicMock()
        liberar = AsyncMock()
        enfileirar = AsyncMock(return_value=True)
        with patch.object(fb, "carregar_por_cnpj_basico", new=AsyncMock(return_value=snap)):
            with patch.object(fb, "liberar_trava_se_fase", new=liberar):
                with patch.object(fb, "enfileirar_sms_pendente", new=enfileirar):
                    out = await fb.tentar_reenfileirar_apos_sms_invalido(
                        MagicMock(),
                        redis,
                        pedido,
                        cnpj_eng=cnpj8,
                    )
        assert out is not None
        assert out[0] == "sms"
        liberar.assert_awaited_once_with(
            redis,
            consulta_id,
            cnpj8,
            fase_pendente_sms("ext-fila-1"),
        )
        enfileirar.assert_awaited()

    asyncio.run(_run())

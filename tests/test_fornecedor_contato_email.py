"""Testes do endpoint e-mail de contato comprador → fornecedor."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config.dependencias import obter_porta_envio_mensagem
from app.config.dependencias_templates import obter_porta_templates
from app.main import app
from app.orquestracao.api.dependencias import _pool, obter_porta_enriquecimento_contato
from app.orquestracao.api.dto.fornecedor_contato_dto import (
    PedidoEmailFornecedorContato,
    RespostaEmailFornecedorContato,
)
from app.orquestracao.api.rotas import fornecedor_contato_rota
from app.orquestracao.servicos import enviar_email_fornecedor_contato as servico
from app.orquestracao.servicos.auxiliares.sanitizar_texto_contato import (
    sanitizar_texto_contato,
)
from app.orquestracao.servicos.fornecedor_contato_constantes import id_externo_fornecedor_contato
from app.templates.modelo import CodigoTipoTemplate, TemplateNotificacao


_CONSULTA = uuid.UUID("11111111-1111-1111-1111-111111111111")
_CNPJ = "12345678"


@pytest.fixture
def client_fornecedor_contato(monkeypatch: pytest.MonkeyPatch):
    async def _executar(*_a, **_k):
        return RespostaEmailFornecedorContato(
            id_externo="AbCdEfGhIjKl",
            id_provedor="zenvia-mock-1",
            tipo_template=CodigoTipoTemplate.CONTATO_FORNECEDOR_SEM_CADASTRO.value,
            destinatario="f@example.com",
            status_ultimo="processando",
            idempotente=False,
        )

    monkeypatch.setattr(
        fornecedor_contato_rota,
        "executar_envio_email_fornecedor_contato",
        _executar,
    )

    async def _pool_fake():
        return AsyncMock()

    app.dependency_overrides[_pool] = _pool_fake
    app.dependency_overrides[obter_porta_envio_mensagem] = lambda: AsyncMock()
    app.dependency_overrides[obter_porta_enriquecimento_contato] = lambda: AsyncMock()

    async def _templates_fake():
        return AsyncMock()

    app.dependency_overrides[obter_porta_templates] = _templates_fake
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_id_externo_com_consulta_deterministico() -> None:
    a = id_externo_fornecedor_contato(_CNPJ, consulta_id=_CONSULTA)
    b = id_externo_fornecedor_contato(_CNPJ, consulta_id=_CONSULTA)
    assert a == b
    assert len(a) == 12
    assert a != id_externo_fornecedor_contato("87654321", consulta_id=_CONSULTA)


def test_id_externo_perfil_so_cnpj() -> None:
    a = id_externo_fornecedor_contato(_CNPJ)
    b = id_externo_fornecedor_contato(_CNPJ, consulta_id=None)
    assert a == b
    assert a != id_externo_fornecedor_contato(_CNPJ, consulta_id=_CONSULTA)


def test_sanitizar_escapa_html_e_converte_quebra() -> None:
    assert sanitizar_texto_contato("<b>x</b>") == "&lt;b&gt;x&lt;/b&gt;"
    assert (
        sanitizar_texto_contato("ola\nmundo", permitir_quebras=True) == "ola<br>mundo"
    )
    assert "<script" not in sanitizar_texto_contato("<script>alert(1)</script>", permitir_quebras=True)


def test_post_fornecedor_contato_email_401() -> None:
    with TestClient(app) as client:
        r = client.post(
            "/v1/interno/orquestracao/fornecedor-contato/email",
            json={
                "cnpj_basico": _CNPJ,
                "mensagem": "oi",
                "nome": "João",
            },
        )
    assert r.status_code == 401


def test_post_fornecedor_contato_email_200_sem_consulta(
    client_fornecedor_contato: TestClient,
) -> None:
    r = client_fornecedor_contato.post(
        "/v1/interno/orquestracao/fornecedor-contato/email",
        headers={"X-Api-Key": "test-api-key-unit"},
        json={
            "cnpj_basico": _CNPJ,
            "mensagem": "quero orçamento",
            "nome": "João",
            "email": "f@example.com",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["destinatario"] == "f@example.com"
    assert body["idempotente"] is False


def test_executar_envio_sem_email_retorna_400(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(servico, "buscar_consulta_por_id", AsyncMock())
    monkeypatch.setattr(servico, "buscar_email_por_id_externo", AsyncMock(return_value=None))
    monkeypatch.setattr(
        servico,
        "buscar_usuario_fornecedor_por_cnpj_basico",
        AsyncMock(side_effect=LookupError),
    )
    monkeypatch.setattr(servico, "garantir_linha_engajamento", AsyncMock())

    class _R:
        email = None
        emails = ()

    monkeypatch.setattr(
        servico,
        "enriquecer_retorno_completo",
        AsyncMock(return_value=_R()),
    )

    with pytest.raises(HTTPException) as ei:
        asyncio.run(
            servico.executar_envio_email_fornecedor_contato(
                AsyncMock(),
                AsyncMock(),
                PedidoEmailFornecedorContato(
                    consulta_id=_CONSULTA,
                    cnpj_basico=_CNPJ,
                    mensagem="oi",
                    nome="João",
                ),
                porta=AsyncMock(),
                templates=AsyncMock(),
            )
        )
    assert ei.value.status_code == 400
    assert "e-mail" in ei.value.detail


def test_executar_envio_sem_consulta_nao_busca_consulta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    buscar = AsyncMock()
    monkeypatch.setattr(servico, "buscar_consulta_por_id", buscar)
    monkeypatch.setattr(
        servico,
        "buscar_email_por_id_externo",
        AsyncMock(
            return_value={
                "id_mensagem_zenvia": "zenvia-perfil",
                "tipo_template": CodigoTipoTemplate.CONTATO_FORNECEDOR_SEM_CADASTRO.value,
                "email_destinatario": "p@example.com",
                "status_ultimo": "entregue",
            }
        ),
    )

    out = asyncio.run(
        servico.executar_envio_email_fornecedor_contato(
            AsyncMock(),
            AsyncMock(),
            PedidoEmailFornecedorContato(
                cnpj_basico=_CNPJ,
                mensagem="oi",
                nome="João",
            ),
            porta=AsyncMock(),
            templates=AsyncMock(),
        )
    )
    buscar.assert_not_awaited()
    assert out.idempotente is True
    assert out.id_externo == id_externo_fornecedor_contato(_CNPJ)


def test_executar_envio_idempotente(monkeypatch: pytest.MonkeyPatch) -> None:
    id_ext = id_externo_fornecedor_contato(_CNPJ, consulta_id=_CONSULTA)
    monkeypatch.setattr(servico, "buscar_consulta_por_id", AsyncMock())
    monkeypatch.setattr(
        servico,
        "buscar_email_por_id_externo",
        AsyncMock(
            return_value={
                "id_mensagem_zenvia": "zenvia-ja",
                "tipo_template": CodigoTipoTemplate.CONTATO_FORNECEDOR_CADASTRADO.value,
                "email_destinatario": "ja@example.com",
                "status_ultimo": "entregue",
            }
        ),
    )

    out = asyncio.run(
        servico.executar_envio_email_fornecedor_contato(
            AsyncMock(),
            AsyncMock(),
            PedidoEmailFornecedorContato(
                consulta_id=_CONSULTA,
                cnpj_basico=_CNPJ,
                mensagem="oi",
                nome="João",
            ),
            porta=AsyncMock(),
            templates=AsyncMock(),
        )
    )
    assert out.idempotente is True
    assert out.id_externo == id_ext
    assert out.id_provedor == "zenvia-ja"
    assert out.destinatario == "ja@example.com"


def test_executar_envio_materializa_e_escapa_html(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.mensageria.api.dto.modelos import CanalMensagem, ResultadoEnvioMensagem

    monkeypatch.setattr(servico, "buscar_consulta_por_id", AsyncMock())
    monkeypatch.setattr(servico, "buscar_email_por_id_externo", AsyncMock(return_value=None))
    monkeypatch.setattr(
        servico,
        "buscar_usuario_fornecedor_por_cnpj_basico",
        AsyncMock(side_effect=LookupError),
    )
    monkeypatch.setattr(servico, "garantir_linha_engajamento", AsyncMock())
    monkeypatch.setattr(servico, "persistir_contatos_iniciais_engajamento", AsyncMock())
    monkeypatch.setattr(servico, "validar_engajamento_antes_envio_email", AsyncMock())
    monkeypatch.setattr(servico, "registrar_email_enviado_apos_sucesso", AsyncMock())
    monkeypatch.setattr(servico, "tocar_engajamento_email", AsyncMock())
    monkeypatch.setattr(servico, "url_login_rastreado_para_id", lambda _id: "https://x/c/token")

    class _R:
        email = "f@example.com"
        emails = ("f@example.com",)

    monkeypatch.setattr(
        servico,
        "enriquecer_retorno_completo",
        AsyncMock(return_value=_R()),
    )

    class _TemplatesFake:
        async def obter_por_tipo_e_variante(self, tipo: str, variante: str) -> TemplateNotificacao:
            assert tipo == CodigoTipoTemplate.CONTATO_FORNECEDOR_SEM_CADASTRO.value
            return TemplateNotificacao(
                id="t1",
                tipo=tipo,
                email="<p>{{ nome }}: {{ mensagem }} <a href=\"{{ url_login }}\">x</a></p>",
                sms="",
            )

    enviado: list = []

    class _PortaFake:
        def enviar_email(self, pedido):
            enviado.append(pedido)
            assert "João" in pedido.corpo_html
            assert "&lt;b&gt;quero&lt;/b&gt;" in pedido.corpo_html
            assert "<b>quero</b>" not in pedido.corpo_html
            return ResultadoEnvioMensagem(
                id_provedor="email-contato-1",
                canal=CanalMensagem.EMAIL,
            )

    out = asyncio.run(
        servico.executar_envio_email_fornecedor_contato(
            AsyncMock(),
            AsyncMock(),
            PedidoEmailFornecedorContato(
                consulta_id=_CONSULTA,
                cnpj_basico=_CNPJ,
                mensagem="<b>quero</b>",
                nome="João",
                email="f@example.com",
            ),
            porta=_PortaFake(),
            templates=_TemplatesFake(),
        )
    )
    assert out.id_provedor == "email-contato-1"
    assert out.tipo_template == CodigoTipoTemplate.CONTATO_FORNECEDOR_SEM_CADASTRO.value
    assert out.idempotente is False
    assert len(enviado) == 1

import asyncio

from app.mensageria.api.dto.modelos import PedidoEnvioEmail
from app.mensageria.servicos.materializar import materializar_email
from app.templates.modelo import CodigoTipoTemplate, TemplateNotificacao


class _TemplatesFake:
    def __init__(self, assunto: str | None = None) -> None:
        self._assunto = assunto

    async def obter_por_tipo(self, codigo: str) -> TemplateNotificacao | None:
        return await self.obter_por_tipo_e_variante(codigo, "simples")

    async def obter_por_tipo_e_variante(self, codigo: str, variante: str) -> TemplateNotificacao | None:
        return TemplateNotificacao(
            id="x",
            tipo=codigo,
            email="<p>Olá {{ uf }}</p>",
            sms="s",
            variante=variante,
            assunto=self._assunto,
        )

    async def listar_todos(self) -> list[TemplateNotificacao]:
        return []


def test_materializar_usa_variante_e_assunto_do_banco() -> None:
    pedido = PedidoEnvioEmail(
        destinatario="a@b.com",
        tipo_template=CodigoTipoTemplate.APARECEU_BUSCA,
        contexto={"uf": "SP"},
        variante="elaborado",
    )
    out = asyncio.run(
        materializar_email(
            pedido,
            _TemplatesFake(assunto="Compradores em {{ uf }} buscam seu setor"),
        )
    )
    assert "SP" in out.corpo_html
    assert out.assunto == "Compradores em SP buscam seu setor"


def test_materializar_fallback_assunto_codigo() -> None:
    pedido = PedidoEnvioEmail(
        destinatario="a@b.com",
        tipo_template=CodigoTipoTemplate.APARECEU_BUSCA,
        contexto={},
        variante="simples",
    )
    out = asyncio.run(materializar_email(pedido, _TemplatesFake(assunto=None)))
    assert "busca" in out.assunto.lower()

from app.mensageria.api.dto.modelos import (
    PedidoEmailProvedor,
    PedidoEnvioEmail,
    PedidoEnvioSms,
    PedidoSmsProvedor,
)
from app.experimentos.variante_email import VARIANTE_PADRAO, normalizar_variante
from app.templates.assunto_email import assunto_email_para_tipo
from app.templates.contexto_genericos import contexto_para_render
from app.templates.porta import PortaTemplates
from app.templates.render import renderizar_template


def _assunto_para_pedido(pedido: PedidoEnvioEmail, assunto_template: str | None) -> str:
    ctx = contexto_para_render(pedido.contexto)
    if assunto_template and assunto_template.strip():
        return renderizar_template(assunto_template.strip(), ctx)
    return assunto_email_para_tipo(pedido.tipo_template)


async def materializar_email(
    pedido: PedidoEnvioEmail,
    templates: PortaTemplates,
) -> PedidoEmailProvedor:
    variante = normalizar_variante(pedido.variante)
    registo = await templates.obter_por_tipo_e_variante(pedido.tipo_template.value, variante)
    if registo is None:
        msg = f"Template desconhecido: {pedido.tipo_template.value} variante={variante}"
        raise ValueError(msg)
    if not registo.email:
        msg = f"O tipo {pedido.tipo_template.value} ({variante}) não possui template de e-mail."
        raise ValueError(msg)
    ctx = contexto_para_render(pedido.contexto)
    corpo = renderizar_template(registo.email, ctx)
    assunto = _assunto_para_pedido(pedido, registo.assunto)
    return PedidoEmailProvedor(
        destinatario=pedido.destinatario,
        assunto=assunto,
        corpo_html=corpo,
        remetente=None,
        id_externo=pedido.id_externo,
    )


async def materializar_sms(
    pedido: PedidoEnvioSms,
    templates: PortaTemplates,
) -> PedidoSmsProvedor:
    registo = await templates.obter_por_tipo(pedido.tipo_template.value)
    if registo is None:
        msg = f"Template desconhecido: {pedido.tipo_template.value}"
        raise ValueError(msg)
    texto = renderizar_template(registo.sms, contexto_para_render(pedido.contexto))
    return PedidoSmsProvedor(
        destinatario=pedido.destinatario,
        texto=texto,
        remetente=None,
        id_externo=pedido.id_externo,
    )

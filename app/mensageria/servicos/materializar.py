from app.mensageria.api.dto.modelos import (
    PedidoEmailProvedor,
    PedidoEnvioEmail,
    PedidoEnvioSms,
    PedidoSmsProvedor,
)
from app.templates.assunto_email import assunto_email_para_tipo
from app.templates.porta import PortaTemplates
from app.templates.render import renderizar_template


async def materializar_email(
    pedido: PedidoEnvioEmail,
    templates: PortaTemplates,
) -> PedidoEmailProvedor:
    registo = await templates.obter_por_tipo(pedido.tipo_template.value)
    if registo is None:
        msg = f"Template desconhecido: {pedido.tipo_template.value}"
        raise ValueError(msg)
    if not registo.email:
        msg = f"O tipo {pedido.tipo_template.value} não possui template de e-mail."
        raise ValueError(msg)
    corpo = renderizar_template(registo.email, pedido.contexto)
    assunto = assunto_email_para_tipo(pedido.tipo_template)
    return PedidoEmailProvedor(
        destinatario=pedido.destinatario,
        assunto=assunto,
        corpo_html=corpo,
        remetente=pedido.remetente,
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
    texto = renderizar_template(registo.sms, pedido.contexto)
    return PedidoSmsProvedor(
        destinatario=pedido.destinatario,
        texto=texto,
        remetente=pedido.remetente,
        id_externo=pedido.id_externo,
    )

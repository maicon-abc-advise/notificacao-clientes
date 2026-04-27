"""Assunto da linha do e-mail (provedor), inferido do código do template."""

from app.templates.modelo import CodigoTipoTemplate

_MAPA: dict[CodigoTipoTemplate, str] = {
    CodigoTipoTemplate.APARECEU_BUSCA: "Você apareceu em uma busca!",
    CodigoTipoTemplate.CREDITOS_NO_FIM: "Seus créditos mensais estão no fim",
    CodigoTipoTemplate.LEMBRETE_CREDITOS_ESGOTADOS: "Lembre-se! Seus créditos mensais acabaram",
}


def assunto_email_para_tipo(tipo: CodigoTipoTemplate) -> str:
    assunto = _MAPA.get(tipo)
    if assunto is None:
        msg = f"Tipo {tipo.value} não tem assunto de e-mail definido no servidor."
        raise ValueError(msg)
    return assunto

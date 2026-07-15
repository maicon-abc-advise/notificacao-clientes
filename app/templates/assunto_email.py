from app.templates.modelo import CodigoTipoTemplate

_MAPA: dict[CodigoTipoTemplate, str] = {
    CodigoTipoTemplate.APARECEU_BUSCA: "Sua empresa apareceu em buscas por fornecedores em sua região",
    CodigoTipoTemplate.APARECEU_BUSCA_SEM_REGISTRO: "Sua empresa apareceu em buscas por fornecedores em sua região",
    CodigoTipoTemplate.CREDITOS_NO_FIM: "Seus créditos mensais estão no fim",
    CodigoTipoTemplate.LEMBRETE_CREDITOS_ESGOTADOS: "Lembre-se! Seus créditos mensais acabaram",
    CodigoTipoTemplate.APRESENTACAO: "Compradores estão procurando fornecedores como você",
    CodigoTipoTemplate.CONTATO_FORNECEDOR_SEM_CADASTRO: (
        "Um comprador quer entrar em contato com você"
    ),
    CodigoTipoTemplate.CONTATO_FORNECEDOR_CADASTRADO: (
        "Um comprador quer entrar em contato com você"
    ),
}

def assunto_email_para_tipo(tipo: CodigoTipoTemplate) -> str:
    assunto = _MAPA.get(tipo)
    if assunto is None:
        msg = f"Tipo {tipo.value} não tem assunto de e-mail definido no servidor."
        raise ValueError(msg)
    return assunto

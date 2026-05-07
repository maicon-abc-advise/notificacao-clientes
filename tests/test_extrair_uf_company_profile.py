from app.orquestracao.externo.company_profile.extrair_uf import extrair_uf_de_company_profile


def test_extrair_uf_chave_raiz() -> None:
    assert extrair_uf_de_company_profile({"uf": "MG"}) == "MG"


def test_extrair_uf_endereco_aninhado() -> None:
    assert extrair_uf_de_company_profile({"endereco": {"uf": "SP"}}) == "SP"


def test_extrair_uf_ausente() -> None:
    assert extrair_uf_de_company_profile({}) is None

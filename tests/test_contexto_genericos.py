from app.templates.contexto_genericos import (
    SEGMENTO_GENERICO,
    UF_GENERICO,
    contexto_para_render,
)


def test_contexto_para_render_preenche_uf_e_segmento_vazios() -> None:
    ctx = contexto_para_render({"uf": "", "segmento": "   ", "url_login": "https://x"})
    assert ctx["uf"] == UF_GENERICO
    assert ctx["segmento"] == SEGMENTO_GENERICO
    assert ctx["url_login"] == "https://x"


def test_contexto_para_render_preserva_valores() -> None:
    ctx = contexto_para_render({"uf": "MG", "segmento": "papel"})
    assert ctx["uf"] == "MG"
    assert ctx["segmento"] == "papel"

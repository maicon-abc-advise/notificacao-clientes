from app.templates.render import renderizar_template


def test_render_substituicao_simples() -> None:
    assert renderizar_template("Olá {{ nome }}", {"nome": "Ana"}) == "Olá Ana"


def test_render_chave_ausente_vazio() -> None:
    assert renderizar_template("{{ a }}", {}) == ""

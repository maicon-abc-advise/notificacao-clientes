import re

_PADRAO = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def renderizar_template(texto: str, contexto: dict[str, str]) -> str:
    """Substitui `{{ chave }}` por `contexto['chave']` (string vazia se ausente)."""

    def substituir(match: re.Match[str]) -> str:
        chave = match.group(1)
        return contexto.get(chave, "")

    return _PADRAO.sub(substituir, texto)

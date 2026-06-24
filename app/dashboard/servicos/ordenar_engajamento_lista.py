from __future__ import annotations

ORDENAR_ENGAJAMENTO_PADRAO = "atualizado"
ORDENAR_ENGAJAMENTO_VALIDOS = frozenset(
    {"atualizado", "aparicoes_total", "aparicoes_30d", "cadastro_recente"},
)


def normalizar_ordenar_engajamento(ordenar: str | None) -> str:
    s = (ordenar or "").strip().lower()
    if s in ("aparicoes_total", "top_buscas", "buscas_total", "buscas_geral"):
        return "aparicoes_total"
    if s in ("aparicoes_30d", "top_buscas_30d", "buscas_30d", "buscas_30"):
        return "aparicoes_30d"
    if s in ("cadastro_recente", "ultimas_cadastradas", "cadastradas"):
        return "cadastro_recente"
    if s in ORDENAR_ENGAJAMENTO_VALIDOS:
        return s
    return ORDENAR_ENGAJAMENTO_PADRAO


def expr_aparicoes_total(*, aparicoes_disponivel: bool) -> str:
    if aparicoes_disponivel:
        return "COALESCE(ap_tot.n, e.aparicoes_busca, 0)"
    return "COALESCE(e.aparicoes_busca, 0)"


def expr_aparicoes_30d(*, aparicoes_disponivel: bool) -> str:
    if aparicoes_disponivel:
        return "COALESCE(ap_30.n, 0)"
    return "0"


def filtros_sql_por_ordenar(
    orden: str,
    *,
    aparicoes_disponivel: bool,
    qual_fornecedores: str,
) -> list[str]:
    if orden == "cadastro_recente":
        return [
            f"EXISTS (SELECT 1 FROM {qual_fornecedores} AS fx WHERE fx.cnpj_basico = e.cnpj_basico)",
        ]
    if orden == "aparicoes_total":
        return [f"{expr_aparicoes_total(aparicoes_disponivel=aparicoes_disponivel)} > 0"]
    if orden == "aparicoes_30d":
        return [f"{expr_aparicoes_30d(aparicoes_disponivel=aparicoes_disponivel)} > 0"]
    return []


def order_by_sql_engajamento(
    orden: str,
    *,
    aparicoes_disponivel: bool,
    col_data_fornecedor: str | None,
) -> str:
    tie = "e.cnpj_basico DESC"
    if orden == "aparicoes_total":
        return f"{expr_aparicoes_total(aparicoes_disponivel=aparicoes_disponivel)} DESC, {tie}"
    if orden == "aparicoes_30d":
        return f"{expr_aparicoes_30d(aparicoes_disponivel=aparicoes_disponivel)} DESC, {tie}"
    if orden == "cadastro_recente" and col_data_fornecedor:
        return f"f.{col_data_fornecedor} DESC NULLS LAST, {tie}"
    if orden == "cadastro_recente":
        return f"au.created_at DESC NULLS LAST, {tie}"
    return f"e.engajamento_atualizado_em DESC NULLS LAST, {tie}"

from app.dashboard.servicos.ordenar_engajamento_lista import (
    expr_aparicoes_30d,
    expr_aparicoes_total,
    filtros_sql_por_ordenar,
    normalizar_ordenar_engajamento,
    order_by_sql_engajamento,
)


def test_normalizar_ordenar_engajamento() -> None:
    assert normalizar_ordenar_engajamento(None) == "atualizado"
    assert normalizar_ordenar_engajamento("") == "atualizado"
    assert normalizar_ordenar_engajamento("top_buscas") == "aparicoes_total"
    assert normalizar_ordenar_engajamento("buscas_30d") == "aparicoes_30d"
    assert normalizar_ordenar_engajamento("ultimas_cadastradas") == "cadastro_recente"
    assert normalizar_ordenar_engajamento("desconhecido") == "atualizado"


def test_filtros_sql_por_ordenar_cadastro() -> None:
    filtros = filtros_sql_por_ordenar(
        "cadastro_recente",
        aparicoes_disponivel=True,
        qual_fornecedores="public.fornecedores",
    )
    assert len(filtros) == 1
    assert "EXISTS" in filtros[0]


def test_order_by_com_coluna_data_fornecedor() -> None:
    sql = order_by_sql_engajamento(
        "cadastro_recente",
        aparicoes_disponivel=True,
        col_data_fornecedor="created_at",
    )
    assert "f.created_at DESC" in sql


def test_exprs_aparicoes() -> None:
    assert "ap_tot" in expr_aparicoes_total(aparicoes_disponivel=True)
    assert "aparicoes_busca" in expr_aparicoes_total(aparicoes_disponivel=False)
    assert "ap_30" in expr_aparicoes_30d(aparicoes_disponivel=True)
    assert expr_aparicoes_30d(aparicoes_disponivel=False) == "0"

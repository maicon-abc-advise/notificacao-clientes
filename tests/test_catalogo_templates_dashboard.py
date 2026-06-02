from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.dashboard.servicos.catalogo_templates_dashboard import (
    montar_contexto_dashboard,
    validar_campos_formulario,
)
from app.templates.modelo import CodigoTipoTemplate


def test_validar_uf_obrigatoria_busca() -> None:
    with pytest.raises(HTTPException) as ei:
        validar_campos_formulario(
            CodigoTipoTemplate.APARECEU_BUSCA,
            nome_fantasia="ACME",
            uf=None,
            segmento="TI",
        )
    assert ei.value.status_code == 400


def test_montar_contexto_busca_email_tem_url_login() -> None:
    ctx = montar_contexto_dashboard(
        CodigoTipoTemplate.APARECEU_BUSCA,
        cnpj_basico="12345678",
        id_externo="abc123def456",
        nome_fantasia="Loja",
        uf="SP",
        segmento="TI",
        canal="email",
    )
    assert ctx["uf"] == "SP"
    assert "clique" in ctx["url_login"]
    assert ctx["saudacao_nome"] == "Loja"


def test_montar_contexto_apresentacao_sms() -> None:
    ctx = montar_contexto_dashboard(
        CodigoTipoTemplate.APRESENTACAO,
        cnpj_basico="12345678",
        id_externo="x" * 12,
        nome_fantasia=None,
        uf=None,
        segmento=None,
        canal="sms",
    )
    assert "url_plataforma" in ctx

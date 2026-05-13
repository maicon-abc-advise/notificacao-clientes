from app.orquestracao.servicos.auxiliares.fragmentar_contatos_recebe_consulta import (
    emails_do_payload,
    garantir_prefixo_55_digitos,
    telefones_normalizados_do_payload,
)


def test_emails_multiplos_espaco() -> None:
    s = "vendas@americaxingu.com.br contato@americaxingu.com.br"
    assert emails_do_payload(s) == ("vendas@americaxingu.com.br", "contato@americaxingu.com.br")


def test_emails_vazio() -> None:
    assert emails_do_payload(None) == ()
    assert emails_do_payload("   ") == ()


def test_telefone_so_digitos_ganha_55() -> None:
    assert telefones_normalizados_do_payload("7532267671") == ("557532267671",)


def test_telefone_varios_parenteses() -> None:
    raw = "(51) 3358.1213 (41) 3316.4500"
    t = telefones_normalizados_do_payload(raw)
    assert t[0].startswith("55")
    assert len(t) == 2


def test_garantir_55_idempotente() -> None:
    assert garantir_prefixo_55_digitos("5511999999999") == "5511999999999"
    assert garantir_prefixo_55_digitos("11999999999") == "5511999999999"


def test_escolher_email_prior_primeiro_fora_do_snap_antes() -> None:
    from app.reenvio.servicos.engajamento_contatos import escolher_email_prior_novos_engajamento

    antes: list = [{"endereco": "a@b.co", "estado": "ATIVO", "ultima_atualizacao_em": "t"}]
    depois = list(antes) + [{"endereco": "c@d.co", "estado": "ATIVO", "ultima_atualizacao_em": "t"}]
    cand = ("a@b.co", "c@d.co")
    assert escolher_email_prior_novos_engajamento(antes, depois, cand) == "c@d.co"


def test_escolher_email_prior_todos_ja_existem_cai_no_melhor() -> None:
    from app.reenvio.servicos.engajamento_contatos import escolher_email_prior_novos_engajamento

    antes = [{"endereco": "a@b.co", "estado": "ATIVO", "ultima_atualizacao_em": "t"}]
    depois = list(antes)
    cand = ("a@b.co",)
    assert escolher_email_prior_novos_engajamento(antes, depois, cand) == "a@b.co"

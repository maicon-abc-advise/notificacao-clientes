from app.orquestracao.servicos.auxiliares.fragmentar_contatos_recebe_consulta import (
    emails_do_payload,
    garantir_prefixo_55_digitos,
    telefones_normalizados_do_payload,
)


def _tel_set(s: str) -> set[str]:
    return set(telefones_normalizados_do_payload(s))


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


def test_telefone_parenteses_nao_colam_com_0800() -> None:
    """Caso analise_telefone.md: não virar um único dígito gigante."""
    raw = "(11) 2188-0500 0800 015 2135"
    assert _tel_set(raw) == {"551121880500", "5508000152135"}


def test_telefone_json_telefone_mas_nao_fax() -> None:
    s = '{"telefone":"+55 47 99123-4567","fax":"4732345678"}'
    assert telefones_normalizados_do_payload(s) == ("5547991234567",)


def test_telefone_mais55_dois_com_barra() -> None:
    s = "+55 (21) 9 8765-4321 / +55 21 3876-5432"
    assert _tel_set(s) == {"5521987654321", "552138765432"}


def test_telefone_wa_me_e_parenteses() -> None:
    s = "Confira https://wa.me/553499112233 e fixo (34) 3232-1010"
    assert _tel_set(s) == {"553499112233", "553432321010"}


def test_telefone_sp_interior_pipe() -> None:
    s = "SP: 11 91234-5678 | Interior: (19) 3542-1100 e (19) 9 8877-6655"
    assert _tel_set(s) == {"5511912345678", "551935421100", "5519988776655"}


def test_telefone_zero_xx_e_tres_parenteses() -> None:
    s = "(0xx11) 2188-0500   0800 015 2135   (11) 99999-0000"
    assert _tel_set(s) == {"551121880500", "5508000152135", "5511999990000"}


def test_telefone_boleto_sem_candidato_util() -> None:
    s = "34191.75123 45675.412345 67895.123456 7 12340001234567"
    assert telefones_normalizados_do_payload(s) == ()


def test_telefone_linha_mista_eua_brasil_somente_br() -> None:
    s = "+1 (415) 555-0199 USA | Brasil +55 11 3003-0202 SAC"
    assert telefones_normalizados_do_payload(s) == ("551130030202",)


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

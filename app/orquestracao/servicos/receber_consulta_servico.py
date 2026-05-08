from __future__ import annotations

import logging
import uuid

import asyncpg
from redis.asyncio import Redis

from app.orquestracao.api.dto.recebe_consulta_dto import RecebeConsultaCorpo, RespostaRecebeConsulta
from app.orquestracao.repositorios.consultas_repo import buscar_por_id as buscar_consulta_por_id
from app.orquestracao.repositorios.engajamento_consulta_repo import (
    carregar_por_cnpj_basico,
    garantir_linha_engajamento,
    incrementar_aparicao_busca,
)
from app.orquestracao.repositorios.fornecedores_repo import (
    buscar_usuario_fornecedor_por_cnpj_basico,
    buscar_usuario_fornecedor_por_cnpj_partes,
)
from app.orquestracao.servicos.auxiliares.decidir_canal_e_cadencia import decidir_canal_e_cadencia
from app.orquestracao.servicos.auxiliares.enfileirar_ou_enviar_interno import (
    enfileirar_email_pendente,
    enfileirar_sms_pendente,
)
from app.orquestracao.servicos.auxiliares.enriquecer_contato_fornecedor import enriquecer_retorno_completo
from app.orquestracao.servicos.auxiliares.montar_pedido_mensagem import (
    montar_pedido_email_apareceu_busca,
    montar_pedido_sms_consultado_sem_email,
)
from app.orquestracao.servicos.auxiliares.resolver_uf_segmento_contexto import (
    resolver_uf_e_segmento_para_contexto,
)
from app.orquestracao.servicos.auxiliares.porta_enriquecimento_contato import PortaEnriquecimentoContato
from app.orquestracao.excecoes import ConsultaJaNotificadaError
from app.reenvio.repositorios.redis_consulta_notificacao import consulta_fornecedor_tem_trava_ativa
from app.reenvio.servicos.engajamento_contatos import (
    agora_iso,
    contatos_iniciais_email,
    contatos_iniciais_sms,
    escolher_email_efetivo,
    escolher_telefone_efetivo,
    estado_granular_email,
    estado_granular_sms,
)
from app.reenvio.servicos.engajamento_fornecedor import persistir_contatos_iniciais_engajamento

_log = logging.getLogger(__name__)
_ORIGEM = "orquestracao-recebe-consulta"


async def executar_receber_consulta(
    pool: asyncpg.Pool,
    redis: Redis,
    porta_enriquecimento: PortaEnriquecimentoContato,
    corpo: RecebeConsultaCorpo,
) -> RespostaRecebeConsulta:
    cnpj = corpo.cnpj_14()
    cnpj_log = cnpj if cnpj else corpo.cnpj_basico
    _log.info(
        "[orquestracao] recebe-consulta inicio id_consulta=%s cnpj=%s",
        corpo.id_consulta,
        cnpj_log,
    )

    await buscar_consulta_por_id(pool, corpo.id_consulta)
    _log.info("[orquestracao] consulta existe id=%s", corpo.id_consulta)

    if await consulta_fornecedor_tem_trava_ativa(
        redis, corpo.id_consulta, corpo.cnpj_basico
    ):
        raise ConsultaJaNotificadaError(f"{corpo.id_consulta}:{corpo.cnpj_basico}")

    fid: uuid.UUID | None = None
    email_f = str(corpo.email_fornecedor).strip() if corpo.email_fornecedor else None
    tel_f = (corpo.telefone_fornecedor or "").strip() or None
    nome_nf = (corpo.nome_fantasia or "").strip() or None
    await garantir_linha_engajamento(
        pool,
        cnpj_basico=corpo.cnpj_basico,
        cnpj=cnpj,
        fornecedor_id=None,
        nome_fantasia=nome_nf,
    )
    await incrementar_aparicao_busca(pool, cnpj_basico=corpo.cnpj_basico, nome_fantasia=nome_nf)
    try:
        if corpo.cnpj_ordem is not None and corpo.cnpj_dv is not None:
            row_f = await buscar_usuario_fornecedor_por_cnpj_partes(
                pool,
                cnpj_basico=corpo.cnpj_basico,
                cnpj_ordem=corpo.cnpj_ordem,
                cnpj_dv=corpo.cnpj_dv,
            )
        else:
            row_f = await buscar_usuario_fornecedor_por_cnpj_basico(
                pool,
                cnpj_basico=corpo.cnpj_basico,
            )
        fid = row_f["fornecedor_id"]
        await garantir_linha_engajamento(
            pool,
            cnpj_basico=corpo.cnpj_basico,
            cnpj=cnpj,
            fornecedor_id=fid,
            nome_fantasia=nome_nf,
        )
        email_f = email_f or ((row_f["email"] or "").strip() or None)
        tel_f = tel_f or ((row_f["telefone"] or "").strip() or None)
    except LookupError:
        _log.info("[orquestracao] usuario_fornecedor ausente para cnpj=%s", cnpj_log)

    usuario_fornecedor_cadastrado = fid is not None
    uf_ctx, segmento_ctx = await resolver_uf_e_segmento_para_contexto(pool, corpo)

    # Sempre: e-mail/telefone do payload entram nas listas (merge com perfil quando faltar dado).
    r = await enriquecer_retorno_completo(
        porta_enriquecimento,
        cnpj_basico=corpo.cnpj_basico,
        email_atual=email_f,
        telefone_atual=tel_f,
    )
    now_iso = agora_iso()
    ce = contatos_iniciais_email(list(r.emails), now_iso=now_iso)
    cs = contatos_iniciais_sms(list(r.telefones), now_iso=now_iso)
    await persistir_contatos_iniciais_engajamento(
        pool,
        cnpj_basico=corpo.cnpj_basico,
        fornecedor_id=fid,
        contatos_email=ce,
        contatos_sms=cs,
    )
    snap = await carregar_por_cnpj_basico(pool, corpo.cnpj_basico)
    email_e = escolher_email_efetivo(snap.contatos_email, email_f)
    tel_e = escolher_telefone_efetivo(snap.contatos_sms, tel_f)

    _log.info(
        "[orquestracao] dados efetivos email=%s telefone=%s",
        email_e,
        tel_e,
    )

    st_e = estado_granular_email(snap.contatos_email, email_e)
    st_s = estado_granular_sms(snap.contatos_sms, tel_e)
    _log.info(
        "[orquestracao] engajamento cnpj_basico=%s fornecedor_id=%s agg_email=%s agg_sms=%s st_gran_email=%s st_gran_sms=%s",
        corpo.cnpj_basico,
        fid,
        snap.engajamento_email,
        snap.engajamento_sms,
        st_e,
        st_s,
    )

    decisao = decidir_canal_e_cadencia(
        engajamento_email_agg=snap.engajamento_email,
        engajamento_sms_agg=snap.engajamento_sms,
        email_efetivo=email_e,
        telefone_efetivo=tel_e,
        estado_granular_email=st_e,
        estado_granular_sms=st_s,
        usuario_fornecedor_cadastrado=usuario_fornecedor_cadastrado,
    )
    _log.info(
        "[orquestracao] decisao canal=%s template=%s motivo=%s",
        decisao.canal,
        decisao.tipo_template.value if decisao.tipo_template else None,
        decisao.motivo,
    )

    if decisao.canal == "nenhum" or decisao.tipo_template is None:
        _log.info("[orquestracao] fim: nada enfileirado (%s)", decisao.motivo)
        return RespostaRecebeConsulta(
            acao="nada",
            id_consulta=corpo.id_consulta,
            motivo=decisao.motivo,
        )

    ext = str(uuid.uuid4())
    if decisao.canal == "email":
        pedido = montar_pedido_email_apareceu_busca(
            corpo,
            destinatario=email_e or "",
            fornecedor_id=fid,
            cnpj_basico=corpo.cnpj_basico,
            id_externo=ext,
            tipo_template=decisao.tipo_template,
            uf=uf_ctx,
            segmento=segmento_ctx,
        )
        ok = await enfileirar_email_pendente(redis, pedido, id_externo=ext, origem=_ORIGEM)
        _log.info(
            "[orquestracao] fim: email enfileirado=%s id_externo=%s dest=%s",
            ok,
            ext,
            email_e,
        )
        return RespostaRecebeConsulta(
            acao="email_enfileirado" if ok else "nada",
            id_consulta=corpo.id_consulta,
            canal="email",
            id_externo=ext if ok else None,
            tipo_template=decisao.tipo_template.value,
            motivo=decisao.motivo if ok else "fila e-mail já continha id_externo",
        )

    pedido_s = montar_pedido_sms_consultado_sem_email(
        corpo,
        destinatario=tel_e or "",
        fornecedor_id=fid,
        cnpj_basico=corpo.cnpj_basico,
        id_externo=ext,
        tipo_template=decisao.tipo_template,
        uf=uf_ctx,
        segmento=segmento_ctx,
    )
    ok = await enfileirar_sms_pendente(redis, pedido_s, id_externo=ext, origem=_ORIGEM)
    _log.info(
        "[orquestracao] fim: sms enfileirado=%s id_externo=%s dest=%s",
        ok,
        ext,
        tel_e,
    )
    return RespostaRecebeConsulta(
        acao="sms_enfileirado" if ok else "nada",
        id_consulta=corpo.id_consulta,
        canal="sms",
        id_externo=ext if ok else None,
        tipo_template=decisao.tipo_template.value,
        motivo=decisao.motivo if ok else "fila SMS já continha id_externo",
    )

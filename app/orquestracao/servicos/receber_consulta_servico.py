from __future__ import annotations

import logging
import uuid

import asyncpg
from redis.asyncio import Redis

from app.orquestracao.api.dto.recebe_consulta_dto import RecebeConsultaCorpo, RespostaRecebeConsulta
from app.orquestracao.repositorios.consultas_repo import buscar_por_id as buscar_consulta_por_id
from app.orquestracao.repositorios.engajamento_consulta_repo import carregar_para_usuario
from app.orquestracao.repositorios.fornecedores_repo import obter_ou_criar_e_incrementar_aparicao
from app.orquestracao.servicos.auxiliares.decidir_canal_e_cadencia import decidir_canal_e_cadencia
from app.orquestracao.servicos.auxiliares.enfileirar_ou_enviar_interno import (
    enfileirar_email_pendente,
    enfileirar_sms_pendente,
)
from app.orquestracao.servicos.auxiliares.enriquecer_contato_fornecedor import enriquecer_se_necessario
from app.orquestracao.servicos.auxiliares.montar_pedido_mensagem import (
    montar_pedido_email_apareceu_busca,
    montar_pedido_sms_consultado_sem_email,
)
from app.orquestracao.servicos.auxiliares.porta_enriquecimento_contato import PortaEnriquecimentoContato
from app.orquestracao.excecoes import ConsultaJaNotificadaError
from app.reenvio.repositorios.redis_consulta_notificacao import consulta_tem_trava_ativa

_log = logging.getLogger(__name__)
_ORIGEM = "orquestracao-recebe-consulta"


async def executar_receber_consulta(
    pool: asyncpg.Pool,
    redis: Redis,
    porta_enriquecimento: PortaEnriquecimentoContato,
    corpo: RecebeConsultaCorpo,
) -> RespostaRecebeConsulta:
    cnpj = corpo.cnpj_14()
    _log.info(
        "[orquestracao] recebe-consulta inicio id_consulta=%s cnpj=%s usuario_id=%s",
        corpo.id_consulta,
        cnpj,
        corpo.usuario_id,
    )

    await buscar_consulta_por_id(pool, corpo.id_consulta)
    _log.info("[orquestracao] consulta existe id=%s", corpo.id_consulta)

    if await consulta_tem_trava_ativa(redis, corpo.id_consulta):
        raise ConsultaJaNotificadaError(str(corpo.id_consulta))

    row_f = await obter_ou_criar_e_incrementar_aparicao(
        pool,
        cnpj=cnpj,
        nome=corpo.nome_fantasia,
        email=str(corpo.email_fornecedor) if corpo.email_fornecedor else None,
        telefone=corpo.telefone_fornecedor,
        usuario_id=corpo.usuario_id,
    )
    _log.info(
        "[orquestracao] fornecedor fornecedor_id=%s email=%s telefone=%s aparicoes=%s ativo=%s",
        row_f["fornecedor_id"],
        row_f["email"],
        row_f["telefone"],
        row_f["aparicoes_busca"],
        row_f["ativo"],
    )

    if not row_f["ativo"]:
        _log.info("[orquestracao] fim: fornecedor inativo — sem fila")
        return RespostaRecebeConsulta(
            acao="nada",
            id_consulta=corpo.id_consulta,
            motivo="fornecedor inativo",
        )

    fid: uuid.UUID = row_f["fornecedor_id"]
    email_f = row_f["email"]
    tel_f = row_f["telefone"]
    email_e, tel_e = await enriquecer_se_necessario(
        pool,
        porta_enriquecimento,
        fornecedor_id=fid,
        cnpj=cnpj,
        email_atual=email_f,
        telefone_atual=tel_f,
    )
    _log.info(
        "[orquestracao] dados apos enriquecimento email=%s telefone=%s",
        email_e,
        tel_e,
    )

    uid = corpo.usuario_id or row_f["usuario_id"]
    snap = await carregar_para_usuario(pool, uid)
    _log.info(
        "[orquestracao] engajamento usuario_id=%s email=%s sms=%s recebe_email=%s",
        uid,
        snap.engajamento_email,
        snap.engajamento_sms,
        snap.recebe_email,
    )

    decisao = decidir_canal_e_cadencia(
        email_efetivo=email_e,
        telefone_efetivo=tel_e,
        recebe_email=snap.recebe_email,
        engajamento_email=snap.engajamento_email,
        engajamento_sms=snap.engajamento_sms,
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
            usuario_id=uid,
            id_externo=ext,
            telefone_sms_fallback=tel_e,
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
        usuario_id=uid,
        id_externo=ext,
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

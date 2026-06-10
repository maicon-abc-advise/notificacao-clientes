"""Pipeline de disparo de ligação via Vapi + registo em ``ligacoes_enviadas``."""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg

from app.config.config import Configuracao
from app.ligacoes.api.dto.modelos import (
    ClienteLigacao,
    MetadadosLigacao,
    PedidoDisparoLigacao,
    SobrescritasAssistente,
    VariaveisAssistente,
)
from app.ligacoes.api.externo.vapi.adaptador_envio import ErroEnvioVapi, disparar_ligacao_vapi
from app.ligacoes.repositorios import postgres_ligacoes_enviadas as repo_pg
from app.ligacoes.servicos.validacao_telefone_voz_br import telefone_para_e164


def fornecedor_id_de_hash(raw: dict[str, str]) -> uuid.UUID | None:
    fid_raw = (raw.get("fornecedor_id") or "").strip()
    if not fid_raw:
        return None
    try:
        return uuid.UUID(fid_raw)
    except ValueError:
        return None


def pedido_de_hash_redis(raw: dict[str, str], id_externo: str) -> PedidoDisparoLigacao:
    tel = telefone_para_e164(raw.get("telefone")) or (raw.get("telefone") or "").strip()
    qtd = raw.get("quantidade_buscas") or "0"
    return PedidoDisparoLigacao(
        customer=ClienteLigacao(number=tel),
        assistantOverrides=SobrescritasAssistente(
            variableValues=VariaveisAssistente(
                cnpj_basico=(raw.get("cnpj_basico") or "").strip(),
                numeroDeBuscas=str(qtd),
                ufBuscada=(raw.get("uf_buscada") or "").strip(),
                segmentoBuscado=(raw.get("segmento_buscado") or "").strip(),
            ),
        ),
        metadata=MetadadosLigacao(id_externo=id_externo),
    )


async def executar_dispatch_call(
    pool: asyncpg.Pool,
    pedido: PedidoDisparoLigacao,
    *,
    config: Configuracao,
    fornecedor_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    tel_e164 = telefone_para_e164(pedido.customer.number)
    if not tel_e164:
        raise ValueError("telefone inválido para ligação de voz (BR)")

    pedido_norm = pedido.model_copy(deep=True)
    pedido_norm.customer.number = tel_e164

    resposta = await disparar_ligacao_vapi(
        pedido_norm,
        api_key=config.vapi_api_key,
        assistant_id=config.vapi_assistant_id,
        phone_number_id=config.vapi_phone_number_id,
    )
    id_chamada_vapi = str(resposta.get("id") or "")
    if not id_chamada_vapi:
        raise ErroEnvioVapi("Resposta Vapi sem call.id")

    vars_v = pedido_norm.assistantOverrides.variableValues

    qtd: int | None = None
    try:
        qtd = int(vars_v.numeroDeBuscas)
    except (TypeError, ValueError):
        qtd = None

    await repo_pg.inserir_apos_disparo(
        pool,
        id_externo=pedido.metadata.id_externo,
        id_chamada_vapi=id_chamada_vapi,
        telefone=tel_e164,
        cnpj_basico=vars_v.cnpj_basico or None,
        fornecedor_id=fornecedor_id,
        quantidade_buscas=qtd,
        uf_buscada=vars_v.ufBuscada or None,
        segmento_buscado=vars_v.segmentoBuscado or None,
    )

    return {
        "ok": True,
        "id_chamada_vapi": id_chamada_vapi,
        "id_externo": pedido.metadata.id_externo,
    }

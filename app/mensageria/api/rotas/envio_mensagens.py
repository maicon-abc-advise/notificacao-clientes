from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis

from app.config.dependencias import obter_porta_envio_mensagem
from app.config.dependencias_templates import PortaTemplatesDep
from app.iam.dependencias import verificar_chamada_interna
from app.mensageria.api.dto.modelos import (
    CanalMensagem,
    PedidoEnvioEmail,
    PedidoEnvioSms,
    ResultadoEnvioMensagem,
)
from app.mensageria.repositorios.postgres_emails_enviados import buscar_por_id_externo as buscar_email_por_id_externo
from app.mensageria.repositorios.postgres_sms_enviados import buscar_por_id_externo as buscar_sms_por_id_externo
from app.mensageria.excecoes.erro import ErroEnvioZenvia
from app.mensageria.servicos.materializar import materializar_email, materializar_sms
from app.mensageria.servicos.porta import PortaEnvioMensagem
from app.reenvio.redis_app import obter_cliente_redis
from app.reenvio.servicos.enfileirar_apos_envio_email import enfileirar_email_enviado_apos_sucesso
from app.reenvio.servicos.engajamento_estado import EngajamentoEmailEstado
from app.reenvio.servicos.engajamento_usuario import tocar_engajamento_email
from app.mensageria.servicos.registrar_email_enviado import registrar_email_enviado_apos_sucesso
from app.mensageria.servicos.registrar_sms_enviado import registrar_sms_enviado_apos_sucesso
from app.templates.conexao import obter_pool

router = APIRouter(
    prefix="/v1/mensagens",
    dependencies=[Depends(verificar_chamada_interna)],
)


async def _pool_mensagens() -> asyncpg.Pool:
    return await obter_pool()

async def _redis_mensagens() -> Redis:
    return await obter_cliente_redis()


def _id_provedor_valido_para_idempotencia(id_z: str | None) -> bool:
    if not id_z:
        return False
    s = str(id_z).strip()
    return bool(s) and not s.startswith("(sem")


@router.post("/email", response_model=ResultadoEnvioMensagem, status_code=status.HTTP_200_OK)
async def post_enviar_email(
    pedido: PedidoEnvioEmail,
    porta: Annotated[PortaEnvioMensagem, Depends(obter_porta_envio_mensagem)],
    templates: PortaTemplatesDep,
    pool: Annotated[asyncpg.Pool, Depends(_pool_mensagens)],
) -> ResultadoEnvioMensagem:
    try:
        if pedido.id_externo:
            existente = await buscar_email_por_id_externo(pool, pedido.id_externo)
            zid = existente["id_mensagem_zenvia"] if existente else None
            if _id_provedor_valido_para_idempotencia(zid):
                return ResultadoEnvioMensagem(
                    id_provedor=str(zid),
                    canal=CanalMensagem.EMAIL,
                    resposta_parcial={"idempotente": True},
                )
        materializado = await materializar_email(pedido, templates)
        resultado = porta.enviar_email(materializado)
        await enfileirar_email_enviado_apos_sucesso(pedido, resultado)
        await registrar_email_enviado_apos_sucesso(pool, pedido, resultado)
        await tocar_engajamento_email(pool, pedido.usuario_id, EngajamentoEmailEstado.EMAIL_ENVIADO_API)
        return resultado
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except ErroEnvioZenvia as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e)[:2000],
        ) from e


@router.post("/sms", response_model=ResultadoEnvioMensagem, status_code=status.HTTP_200_OK)
async def post_enviar_sms(
    pedido: PedidoEnvioSms,
    porta: Annotated[PortaEnvioMensagem, Depends(obter_porta_envio_mensagem)],
    templates: PortaTemplatesDep,
    pool: Annotated[asyncpg.Pool, Depends(_pool_mensagens)],
    redis: Annotated[Redis, Depends(_redis_mensagens)],
) -> ResultadoEnvioMensagem:
    try:
        if pedido.id_externo:
            existente = await buscar_sms_por_id_externo(pool, pedido.id_externo)
            zid = existente["id_mensagem_zenvia"] if existente else None
            if _id_provedor_valido_para_idempotencia(zid):
                return ResultadoEnvioMensagem(
                    id_provedor=str(zid),
                    canal=CanalMensagem.SMS,
                    resposta_parcial={"idempotente": True},
                )
        materializado = await materializar_sms(pedido, templates)
        resultado = porta.enviar_sms(materializado)
        await registrar_sms_enviado_apos_sucesso(pool, redis, pedido, resultado)
        return resultado
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except ErroEnvioZenvia as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e)[:2000],
        ) from e

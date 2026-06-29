from __future__ import annotations
import logging
import asyncpg

from app.mensageria.api.dto.modelos import CanalMensagem, PedidoEnvioEmail, ResultadoEnvioMensagem
from app.mensageria.repositorios.postgres_emails_enviados import inserir_ou_atualizar_apos_envio_api
from app.mensageria.repositorios.postgres_fornecedores import resolver_cnpj_basico_para_envio_mensagem

_log = logging.getLogger(__name__)


async def registrar_email_enviado_apos_sucesso(
    pool: asyncpg.Pool,
    pedido: PedidoEnvioEmail,
    resultado: ResultadoEnvioMensagem,
    *,
    cnpj_basico_resolvido: str | None = None,
) -> None:
    if resultado.canal != CanalMensagem.EMAIL:
        return
    if not pedido.id_externo:
        return
    msg_id = resultado.id_provedor
    if not msg_id or msg_id.startswith("(sem"):
        _log.warning(
            "E-mail sem id Zenvia; não gravado em emails_enviados. id_externo=%s",
            pedido.id_externo,
        )
        return

    cnpj = (cnpj_basico_resolvido or "").strip() or None
    if not cnpj:
        cnpj = await resolver_cnpj_basico_para_envio_mensagem(
            pool,
            cnpj_basico=pedido.cnpj_basico,
            fornecedor_id=pedido.fornecedor_id,
        )

    await inserir_ou_atualizar_apos_envio_api(
        pool,
        id_externo=pedido.id_externo,
        email_destinatario=pedido.destinatario,
        tipo_template=pedido.tipo_template.value,
        contexto=dict(pedido.contexto),
        remetente=pedido.remetente,
        id_mensagem_zenvia=msg_id,
        fornecedor_id=pedido.fornecedor_id,
        cnpj_basico=cnpj,
        variante=pedido.variante,
        experimento_id=pedido.experimento_id,
    )

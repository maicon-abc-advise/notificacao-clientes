"""Rotinas WhatsApp: envio de pendentes e atualização de conversas (separadas)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from typing import Any, Literal

import asyncpg

from app.config.config import Configuracao
from app.ligacoes.servicos.entrada_ligacao_apos_falha_whatsapp import convidar_ligacao_apos_falha_whatsapp
from app.orquestracao.repositorios.fornecedores_repo import buscar_usuario_fornecedor_por_cnpj_basico
from app.whatsapp.api.externo.evolution.adaptador_evolution import (
    ErroEvolutionAPI,
    buscar_mensagens_chat,
    jid_whatsapp,
)
from app.whatsapp.repositorios import postgres_whatsapp_envios as repo
from app.whatsapp.repositorios.postgres_whatsapp_envios import cnpj_de_row
from app.whatsapp.repositorios.redis_historico_whatsapp import (
    append_mensagem_agente_historico_redis,
    buscar_historico_redis_n8n,
)
from app.whatsapp.servicos.conversation_agent import AgentDecision, decide_next_step
from app.whatsapp.servicos.executar_envio_whatsapp import enviar_mensagem_inicial
from app.whatsapp.servicos.telefone_whatsapp import normalizar_telefone_whatsapp, variantes_telefone_whatsapp
from app.whatsapp.servicos.tocar_engajamento_whatsapp import tocar_engajamento_whatsapp, WhatsappEngajamentoEstado

_log = logging.getLogger(__name__)

TipoRotina = Literal["enviar_pendentes", "atualizar_conversas", "completa"]


@dataclass
class RoutineAction:
    id: str
    cnpj_basico: str
    action: str
    detail: str
    status_antes: str | None = None
    status_depois: str | None = None
    agent_source: str | None = None
    agent_debug: dict[str, Any] | None = None


@dataclass
class RoutineResult:
    tipo: TipoRotina = "completa"
    processed: int = 0
    actions: list[RoutineAction] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    execucao_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tipo": self.tipo,
            "execucao_id": self.execucao_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "processed": self.processed,
            "actions": [
                {
                    "id": a.id,
                    "cnpj_basico": a.cnpj_basico,
                    "action": a.action,
                    "detail": a.detail,
                    "status_antes": a.status_antes,
                    "status_depois": a.status_depois,
                    "agent_source": a.agent_source,
                    "agent_debug": a.agent_debug,
                }
                for a in self.actions
            ],
            "errors": list(self.errors),
        }


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _cooldown_passed(updated_at: datetime | None, now: datetime, hours: int) -> bool:
    if updated_at is None:
        return True
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    return (now - updated_at).total_seconds() / 3600 >= hours


@dataclass
class ConversationFetchResult:
    messages: list[dict]
    source: str
    fetch_debug: dict[str, Any] = field(default_factory=dict)


async def _fetch_conversation(cfg: Configuracao, telefone: str) -> ConversationFetchResult:
    redis_result = await buscar_historico_redis_n8n(telefone)
    fetch_debug: dict[str, Any] = dict(redis_result.debug_dict())
    if redis_result.messages:
        return ConversationFetchResult(redis_result.messages, "redis_n8n", fetch_debug)

    fetch_debug["redis_fallback_evolution"] = True
    try:
        sem_nove, com_nove = variantes_telefone_whatsapp(telefone)
    except ValueError:
        return ConversationFetchResult([], "nenhuma", fetch_debug)

    for variant in (com_nove, sem_nove):
        try:
            messages = await buscar_mensagens_chat(cfg, variant)
            if messages:
                fetch_debug["evolution_variant"] = variant
                fetch_debug["evolution_mensagens_total"] = len(messages)
                return ConversationFetchResult(messages, "evolution", fetch_debug)
        except ErroEvolutionAPI as exc:
            _log.warning("Falha ao buscar conversa Evolution %s: %s", variant, exc)
    return ConversationFetchResult([], "nenhuma", fetch_debug)


async def _cadastrou(pool: asyncpg.Pool, cnpj_basico: str) -> bool:
    try:
        await buscar_usuario_fornecedor_por_cnpj_basico(pool, cnpj_basico=cnpj_basico)
        return True
    except LookupError:
        return False


def _mesclar_resultados(*partes: RoutineResult) -> RoutineResult:
    if len(partes) == 1:
        return partes[0]
    base = RoutineResult(
        tipo="completa",
        started_at=min(p.started_at for p in partes if p.started_at),
        finished_at=max(p.finished_at for p in partes if p.finished_at),
    )
    for p in partes:
        base.processed += p.processed
        base.actions.extend(p.actions)
        base.errors.extend(p.errors)
        if p.execucao_id and not base.execucao_id:
            base.execucao_id = p.execucao_id
    return base


async def _persistir_resultado(pool: asyncpg.Pool, result: RoutineResult) -> None:
    result.finished_at = result.finished_at or _utcnow()
    try:
        eid = await repo.salvar_execucao_rotina(
            pool,
            resultado=result.to_dict(),
            iniciado_em=result.started_at or result.finished_at,
            finalizado_em=result.finished_at,
        )
        result.execucao_id = str(eid)
    except Exception as exc:
        result.errors.append(f"Log rotina não salvo: {exc}")


async def executar_envio_pendentes_whatsapp(
    pool: asyncpg.Pool,
    cfg: Configuracao,
    *,
    envio_id: str | None = None,
    limite: int | None = None,
) -> RoutineResult:
    """Valida número e envia mensagem inicial para registros ``pendente``.

    Com ``limite``, processa só os N pendentes mais recentes (``updated_at``).
    """
    result = RoutineResult(tipo="enviar_pendentes", started_at=_utcnow())
    telefones_contatados: set[str] = set()

    if envio_id:
        row = await repo.buscar_por_id(pool, envio_id)
        candidatos = [row] if row and str(row["status"]) == "pendente" else []
    else:
        candidatos = await repo.listar_pendentes_para_envio(pool, limite=limite)

    for row in candidatos:
        if row is None:
            continue
        result.processed += 1
        rid = str(row["id"])
        cnpj = cnpj_de_row(row)
        status = str(row["status"])
        tel = str(row["numero_telefone"])

        try:
            if int(row.get("outros_contatados_mesmo_tel") or 0) > 0:
                result.actions.append(
                    RoutineAction(
                        id=rid,
                        cnpj_basico=cnpj,
                        action="serializado_aguardando",
                        detail="Outro CNPJ contatado neste telefone",
                        status_antes=status,
                        status_depois=status,
                    )
                )
                continue
            if tel in telefones_contatados:
                continue

            envio = await enviar_mensagem_inicial(pool, cfg, row["id"])
            acao = envio.get("acao", "enviar_mensagem")
            depois = "contatado" if envio.get("mensagem_enviada") else status
            if envio.get("mensagem_enviada"):
                telefones_contatados.add(tel)
            result.actions.append(
                RoutineAction(
                    id=rid,
                    cnpj_basico=cnpj,
                    action=acao,
                    detail=str(envio),
                    status_antes=status,
                    status_depois=depois,
                )
            )
        except Exception as exc:
            _log.exception("Erro envio pendente WhatsApp id=%s", rid)
            result.errors.append(f"{rid}: {exc}")

    await _persistir_resultado(pool, result)
    return result


async def executar_atualizar_conversas_whatsapp(
    pool: asyncpg.Pool,
    cfg: Configuracao,
    *,
    envio_id: str | None = None,
) -> RoutineResult:
    """Lê chat (Redis n8n, fallback Evolution) e atualiza funil para registros ``contatado``.

    Com ``envio_id`` (ação manual por registro), ignora o cooldown configurado.
    """
    result = RoutineResult(tipo="atualizar_conversas", started_at=_utcnow())
    now = result.started_at
    cooldown_h = cfg.routine_cooldown_hours

    if envio_id:
        row = await repo.buscar_por_id(pool, envio_id)
        candidatos = [row] if row and str(row["status"]) == "contatado" else []
    else:
        candidatos = await repo.listar_contatados_para_atualizacao(pool, max_falhas=cfg.routine_max_falhas)

    for row in candidatos:
        if row is None:
            continue
        result.processed += 1
        rid = str(row["id"])
        cnpj = cnpj_de_row(row)
        status = str(row["status"])
        tel = str(row["numero_telefone"])

        try:
            if await _cadastrou(pool, cnpj):
                await _concluir_com_etapa(
                    pool, row["id"], resultado="sucesso", max_etapas=cfg.routine_max_falhas
                )
                await tocar_engajamento_whatsapp(
                    pool,
                    row.get("fornecedor_id"),
                    cnpj,
                    WhatsappEngajamentoEstado.WHATSAPP_CONCLUIDO_SUCESSO,
                    telefone=tel,
                )
                result.actions.append(
                    RoutineAction(
                        id=rid,
                        cnpj_basico=cnpj,
                        action="concluir_sucesso",
                        detail="Fornecedor cadastrado",
                        status_antes=status,
                        status_depois="concluido_sucesso",
                        agent_source="regra",
                    )
                )
                continue

            if envio_id is None and not _cooldown_passed(row["updated_at"], now, cooldown_h):
                result.actions.append(
                    RoutineAction(
                        id=rid,
                        cnpj_basico=cnpj,
                        action="cooldown",
                        detail=f"Aguardando cooldown de {cooldown_h}h",
                        status_antes=status,
                        status_depois=status,
                    )
                )
                continue

            fetch = await _fetch_conversation(cfg, tel)
            ctx = {
                "cnpj_basico": cnpj,
                "status": status,
                "cadastrado": False,
                "telefone": tel,
                "remote_jid": jid_whatsapp(tel),
                "conversation_source": fetch.source,
                "conversation_fetch_debug": fetch.fetch_debug,
            }
            decision = decide_next_step(fetch.messages, ctx, since=row["updated_at"], cfg=cfg)
            await _aplicar_decisao(pool, cfg, row, decision, result)

        except Exception as exc:
            _log.exception("Erro atualizar conversa WhatsApp id=%s", rid)
            result.errors.append(f"{rid}: {exc}")

    await _persistir_resultado(pool, result)
    return result


async def executar_rotina_whatsapp(
    pool: asyncpg.Pool,
    cfg: Configuracao,
    *,
    envio_id: str | None = None,
    limite_envio: int | None = None,
) -> RoutineResult:
    """Wrapper: envio de pendentes + atualização de conversas."""
    envio = await executar_envio_pendentes_whatsapp(
        pool, cfg, envio_id=envio_id, limite=limite_envio
    )
    envio.execucao_id = None
    conversas = await executar_atualizar_conversas_whatsapp(pool, cfg, envio_id=envio_id)
    conversas.execucao_id = None
    merged = _mesclar_resultados(envio, conversas)
    await _persistir_resultado(pool, merged)
    return merged


async def _concluir_com_etapa(
    pool: asyncpg.Pool,
    envio_id: Any,
    *,
    resultado: str,
    max_etapas: int,
) -> asyncpg.Record | None:
    return await repo.registrar_resultado_etapa(pool, envio_id, resultado, max_etapas=max_etapas)


async def _aplicar_decisao(
    pool: asyncpg.Pool,
    cfg: Configuracao,
    row: asyncpg.Record,
    decision: AgentDecision,
    result: RoutineResult,
) -> None:
    rid = str(row["id"])
    cnpj = cnpj_de_row(row)
    status = str(row["status"])
    tel = str(row["numero_telefone"])
    step = decision.proximo_passo
    detail = f"{decision.motivo} [{decision.source}]"
    dbg = decision.debug

    if step == "concluir_sucesso":
        if await _cadastrou(pool, cnpj):
            await _concluir_com_etapa(
                pool, row["id"], resultado="sucesso", max_etapas=cfg.routine_max_falhas
            )
            await tocar_engajamento_whatsapp(
                pool, row.get("fornecedor_id"), cnpj, WhatsappEngajamentoEstado.WHATSAPP_CONCLUIDO_SUCESSO, telefone=tel
            )
            result.actions.append(
                RoutineAction(
                    rid, cnpj, "concluir_sucesso", detail, status, "concluido_sucesso", decision.source, dbg
                )
            )
        else:
            atualizado = await _concluir_com_etapa(
                pool, row["id"], resultado="sucesso_sem_cadastro", max_etapas=cfg.routine_max_falhas
            )
            novo = str(atualizado["status"]) if atualizado else "pendente"
            result.actions.append(
                RoutineAction(
                    rid,
                    cnpj,
                    "sucesso_sem_cadastro_retorna_pendente",
                    f"{detail} (cadastro não confirmado no banco)",
                    status,
                    novo,
                    decision.source,
                    dbg,
                )
            )
        return

    if step == "concluir_falha":
        await _concluir_com_etapa(pool, row["id"], resultado="falha", max_etapas=cfg.routine_max_falhas)
        await tocar_engajamento_whatsapp(
            pool, row.get("fornecedor_id"), cnpj, WhatsappEngajamentoEstado.WHATSAPP_CONCLUIDO_FALHA, telefone=tel
        )
        result.actions.append(
            RoutineAction(rid, cnpj, "concluir_falha", detail, status, "concluido_falha", decision.source, dbg)
        )
        return

    if step == "marcar_falha_retornar_pendente":
        resultado = decision.resultado_etapa or "inconclusivo"
        if resultado not in ("ignorado", "inconclusivo"):
            resultado = "inconclusivo"
        atualizado = await repo.registrar_resultado_etapa(
            pool, row["id"], resultado, max_etapas=cfg.routine_max_falhas
        )
        novo = str(atualizado["status"]) if atualizado else status
        ligacao: dict[str, Any] | None = None
        if novo == "concluido_falha" and atualizado is not None:
            await tocar_engajamento_whatsapp(
                pool,
                row.get("fornecedor_id"),
                cnpj,
                WhatsappEngajamentoEstado.WHATSAPP_CONCLUIDO_FALHA,
                telefone=tel,
            )
            ligacao = await convidar_ligacao_apos_falha_whatsapp(
                pool,
                atualizado,
                origem="whatsapp_etapas_esgotadas",
            )
        result.actions.append(
            RoutineAction(
                rid,
                cnpj,
                "etapa_retorna_pendente",
                f"{detail}; ligacao={ligacao['retorno'] if ligacao else '—'}",
                status,
                novo,
                decision.source,
                dbg,
            )
        )
        return

    if step == "enviar_resposta" and decision.mensagem_resposta:
        try:
            normalizar_telefone_whatsapp(tel)
            from app.whatsapp.api.externo.evolution.adaptador_evolution import enviar_texto

            await enviar_texto(cfg, tel, decision.mensagem_resposta)
            try:
                await append_mensagem_agente_historico_redis(tel, decision.mensagem_resposta)
            except Exception as exc:
                _log.warning("Histórico Redis não gravado após enviar_resposta id=%s: %s", rid, exc)
            await repo.atualizar_status(pool, row["id"], status="contatado")
            result.actions.append(
                RoutineAction(rid, cnpj, "enviar_resposta", detail, status, "contatado", decision.source, dbg)
            )
        except ErroEvolutionAPI as exc:
            result.errors.append(f"{rid}: {exc}")
        return

    action = "aguardar_resposta" if step == "aguardar_resposta" else "sem_acao"
    result.actions.append(RoutineAction(rid, cnpj, action, detail, status, status, decision.source, dbg))

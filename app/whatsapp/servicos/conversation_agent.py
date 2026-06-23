"""Agente de decisão do funil WhatsApp (heurística + OpenAI opcional)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.config.config import Configuracao
from app.whatsapp.servicos.conversation_analysis import (
    AnalyzedConversation,
    ConversationOutcome,
    analyze_conversation,
)

_log = logging.getLogger(__name__)

VALID_STEPS = frozenset({
    "concluir_sucesso",
    "concluir_falha",
    "marcar_falha_retornar_pendente",
    "aguardar_resposta",
    "enviar_resposta",
    "sem_acao",
})

_CLAUDIA_CONTEXT = """
# CONTEXTO E PERSONA (referência — use só se for redigir mensagem_resposta)
Você representa a Cláudia, especialista em relacionamento com fornecedores da BuscaFornecedor.com.br.
Tom: humano, prestativo, B2B, direto. Mensagens curtas para WhatsApp — sem paredões de texto.

# O PRODUTO
- Plataforma de IA que conecta compradores corporativos a fornecedores qualificados.
- Perfis de fornecedor podem existir de forma automatizada; o cadastro gratuito ativa/reivindica o perfil.
- Dashboard gratuito: volume de buscas e nichos em que a empresa foi indicada.
- Cadastro e painel são gratuitos; créditos/planos só para contato direto avançado (mencione se perguntarem).
- Link sempre: https://buscafornecedor.com.br/fornecedores (use 👉 antes do link nas respostas).
"""

_ANALYSIS_INSTRUCTIONS = """
# MODO ANÁLISE — ROTINA AUTOMÁTICA DO FUNIL WHATSAPP

Você NÃO está conversando com o fornecedor agora. Sua única tarefa é analisar o histórico e decidir
o próximo passo da rotina automática que busca converter o fornecedor para se cadastrar em
https://buscafornecedor.com.br/fornecedores

## FORMATO DE SAÍDA (OBRIGATÓRIO)

Retorne APENAS um JSON válido, sem markdown, sem texto fora do JSON:

{
  "proximo_passo": "<um dos valores abaixo, EXATAMENTE como escrito>",
  "resultado_etapa": null,
  "motivo": "explicação curta em português (1-2 frases)",
  "mensagem_resposta": null
}

CRÍTICO: "proximo_passo" deve ser EXATAMENTE uma destas strings (copie literalmente):
- "concluir_sucesso"
- "concluir_falha"
- "marcar_falha_retornar_pendente"
- "aguardar_resposta"
- "enviar_resposta"
- "sem_acao"

NUNCA invente outros valores (ex.: "realizar cadastro", "enviar link", "aguardar cadastro").
Qualquer valor fora da lista invalida a rotina.

## SIGNIFICADO DE CADA proximo_passo

"concluir_sucesso"
  Fornecedor confirmou cadastro, disse que vai se cadastrar de forma definitiva, demonstrou interesse
  claro e encerrável ("já me cadastrei", "vou cadastrar agora", "já criei a conta"), OU cadastrado=true
  no contexto. Não use se ainda há dúvidas abertas ou se só a Cláudia falou.

"concluir_falha"
  Recusa explícita, pediu para parar, bloqueou, ou sem perspectiva real
  ("não tenho interesse", "pare de mandar", "não atendemos esse segmento").

"marcar_falha_retornar_pendente"
  Fornecedor ignorou a proposta (sem resposta útil) ou manteve a conversa sem confirmação nem recusa
  clara — deve ser recontatado depois. Preencha "resultado_etapa" com "ignorado" ou "inconclusivo":
  - "ignorado": não respondeu, resposta irrelevante ou só emoji/vago sem diálogo
  - "inconclusivo": respondeu e manteve a conversa, mas sem aceitar nem recusar

"aguardar_resposta"
  Fornecedor respondeu recentemente com dúvida ou abertura, a Cláudia já respondeu adequadamente,
  e o próximo movimento é do fornecedor — não envie nova mensagem agora.

"enviar_resposta"
  Fornecedor fez pergunta, expressou dúvida ou deu abertura que AINDA NÃO foi respondida pela Cláudia
  de forma adequada — preencha "mensagem_resposta" como a Cláudia (curta, humana, CTA com 👉 e link).
  Obrigatório incluir texto em mensagem_resposta.

"sem_acao"
  Ainda não há mensagem relevante do fornecedor no histórico, ou só mensagens da Cláudia/plataforma.

## REGRAS DE DECISÃO

1. Foque nas mensagens rotuladas "Fornecedor:" — são as respostas do contato.
2. Mensagens "Cláudia:" são da plataforma; não contem como resposta do fornecedor.
3. Ignore ruído óbvio: testes internos, conversas sobre bugs do sistema, mensagens de comprador
   (quando o fornecedor deixa claro que não é o público-alvo), meta-conversa de equipe técnica.
4. Priorize converter para cadastro; não encerre cedo demais com concluir_falha.
5. Não invente dados de compradores, endereços, escopos ou oportunidades específicas.
6. Se cadastrado=true no contexto → "concluir_sucesso" (não redija mensagem).
7. Se proximo_passo ≠ "enviar_resposta" → mensagem_resposta DEVE ser null.
8. Se proximo_passo = "enviar_resposta" → mensagem_resposta é OBRIGATÓRIA (texto pronto para WhatsApp).
9. Se proximo_passo = "concluir_sucesso" → resultado_etapa = "sucesso".
10. Se proximo_passo = "concluir_falha" → resultado_etapa = "falha".
11. Se proximo_passo = "marcar_falha_retornar_pendente" → resultado_etapa = "ignorado" ou "inconclusivo".
12. Caso contrário → resultado_etapa = null.

## EXEMPLOS DE SAÍDA CORRETA

Fornecedor: "Já criei minha conta, obrigado"
→ {"proximo_passo": "concluir_sucesso", "resultado_etapa": "sucesso", "motivo": "Fornecedor confirmou cadastro.", "mensagem_resposta": null}

Fornecedor: "Não tenho interesse, pare de mandar"
→ {"proximo_passo": "concluir_falha", "resultado_etapa": "falha", "motivo": "Recusa explícita.", "mensagem_resposta": null}

Fornecedor: "Como funciona? É pago?"
→ {"proximo_passo": "enviar_resposta", "motivo": "Dúvidas sobre funcionamento e custo sem resposta adequada.", "mensagem_resposta": "Oi! Sou a Cláudia do BuscaFornecedor.com.br. O cadastro e o painel são 100% gratuitos — você vê as indicações do seu setor. Planos avançados existem só se quiser contato direto ativo. Pode criar seu perfil aqui 👉 https://buscafornecedor.com.br/fornecedores"}

Fornecedor respondeu, Cláudia já explicou tudo, fornecedor não falou de novo
→ {"proximo_passo": "aguardar_resposta", "motivo": "Aguardando retorno após resposta enviada.", "mensagem_resposta": null}

Só mensagens da Cláudia, nenhuma do fornecedor
→ {"proximo_passo": "marcar_falha_retornar_pendente", "resultado_etapa": "ignorado", "motivo": "Fornecedor ignorou a proposta.", "mensagem_resposta": null}
"""

_SYSTEM_PROMPT = _CLAUDIA_CONTEXT.strip() + "\n\n" + _ANALYSIS_INSTRUCTIONS.strip()


def _format_context(ctx: dict, since: datetime | None) -> str:
    since_label = since.isoformat() if isinstance(since, datetime) else "nunca"
    return (
        f"CNPJ: {ctx.get('cnpj_basico') or '—'}\n"
        f"Status no funil: {ctx.get('status') or '—'}\n"
        f"Cadastrado na plataforma: {'sim' if ctx.get('cadastrado') else 'não'}\n"
        f"Telefone: {ctx.get('telefone') or '—'}\n"
        f"Último contato/envio da rotina em: {since_label}\n"
        f"Fonte do histórico: {ctx.get('conversation_source') or '—'}\n"
    )


def _build_user_prompt(ctx: dict, thread: str, since: datetime | None) -> str:
    return (
        f"{_format_context(ctx, since)}\n"
        f"--- HISTÓRICO WHATSAPP (Fornecedor = contato; Cláudia = plataforma) ---\n"
        f"{thread}\n"
        f"--- FIM DO HISTÓRICO ---\n"
        "Com base no histórico acima, decida proximo_passo (valor exato da lista permitida), "
        "resultado_etapa quando aplicável, motivo e mensagem_resposta se aplicável."
    )


@dataclass
class AgentDecision:
    proximo_passo: str
    motivo: str
    mensagem_resposta: str | None = None
    resultado_etapa: str | None = None
    outcome: ConversationOutcome = ConversationOutcome.INCONCLUSIVO
    source: str = "heuristica"
    debug: dict[str, Any] | None = None


def _resultado_etapa_de_outcome(outcome: ConversationOutcome) -> str | None:
    mapping = {
        ConversationOutcome.SUCESSO: "sucesso",
        ConversationOutcome.FALHA: "falha",
        ConversationOutcome.IGNORADO: "ignorado",
        ConversationOutcome.INCONCLUSIVO: "inconclusivo",
    }
    return mapping.get(outcome)


def _legacy_decision(analysis: AnalyzedConversation) -> AgentDecision:
    mapping = {
        ConversationOutcome.SUCESSO: "concluir_sucesso",
        ConversationOutcome.FALHA: "concluir_falha",
        ConversationOutcome.IGNORADO: "marcar_falha_retornar_pendente",
        ConversationOutcome.INCONCLUSIVO: "marcar_falha_retornar_pendente",
        ConversationOutcome.SEM_CONVERSA: "sem_acao",
    }
    step = mapping[analysis.outcome]
    return AgentDecision(
        proximo_passo=step,
        motivo=analysis.reason,
        mensagem_resposta=None,
        resultado_etapa=_resultado_etapa_de_outcome(analysis.outcome),
        outcome=analysis.outcome,
        source="heuristica",
    )


def _format_thread(messages: list[dict]) -> str:
    thread_lines: list[str] = []
    for msg in messages:
        incoming = not (msg.get("key") or {}).get("fromMe", msg.get("fromMe", False))
        prefix = "Fornecedor" if incoming else "Cláudia"
        text = msg.get("message", {})
        if isinstance(text, dict):
            text = text.get("conversation") or text.get("extendedTextMessage", {}).get("text") or ""
        thread_lines.append(f"{prefix}: {text}")
    return "\n".join(thread_lines) or "(vazio)"


def _debug_base(messages: list[dict], ctx: dict) -> dict[str, Any]:
    source = ctx.get("conversation_source") or "desconhecida"
    debug: dict[str, Any] = {
        "telefone": ctx.get("telefone"),
        "remote_jid": ctx.get("remote_jid"),
        "conversation_source": source,
        "mensagens_total": len(messages),
        "thread": _format_thread(messages),
    }
    fetch_debug = ctx.get("conversation_fetch_debug")
    if isinstance(fetch_debug, dict):
        debug.update(fetch_debug)
    if source == "evolution" or ctx.get("redis_fallback_evolution"):
        debug["evolution_filtro"] = {"where": {"key": {"remoteJid": ctx.get("remote_jid")}}}
        debug["evolution_mensagens_total"] = len(messages)
    return debug


def decide_next_step(
    messages: list[dict],
    ctx: dict,
    *,
    since: datetime | None = None,
    cfg: Configuracao | None = None,
) -> AgentDecision:
    if ctx.get("cadastrado"):
        return AgentDecision(
            proximo_passo="concluir_sucesso",
            motivo="Fornecedor já cadastrado na plataforma",
            resultado_etapa="sucesso",
            outcome=ConversationOutcome.SUCESSO,
            source="regra",
            debug={
                "openai_nao_chamada": "fornecedor já cadastrado na plataforma",
                "evolution_mensagens_total": len(messages),
            },
        )

    debug = _debug_base(messages, ctx)
    api_key = (cfg.openai_api_key if cfg else "") or ""
    if not api_key.strip():
        analysis = analyze_conversation(messages, since=since)
        decision = _legacy_decision(analysis)
        debug["modo"] = "heuristica"
        debug["analise"] = {
            "outcome": analysis.outcome.value,
            "motivo": analysis.reason,
            "mensagens_fornecedor": analysis.incoming_count,
        }
        decision.debug = debug
        return decision

    try:
        from openai import OpenAI

        thread = debug["thread"]
        prompt = _build_user_prompt(ctx, thread, since)
        model = (cfg.openai_model if cfg else "gpt-4o-mini") or "gpt-4o-mini"
        openai_request = {
            "model": model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.3,
        }
        debug["modo"] = "openai"
        debug["openai_request"] = openai_request

        client = OpenAI(api_key=api_key.strip())
        resp = client.chat.completions.create(**openai_request)
        parsed = json.loads(resp.choices[0].message.content or "{}")
        debug["openai_resposta"] = parsed

        step = str(parsed.get("proximo_passo", "sem_acao")).strip()
        if step not in VALID_STEPS:
            step = "sem_acao"

        motivo = str(parsed.get("motivo") or "Sem motivo informado").strip()
        mensagem = parsed.get("mensagem_resposta")
        if mensagem is not None:
            mensagem = str(mensagem).strip() or None

        if step == "enviar_resposta" and not mensagem:
            step = "aguardar_resposta"
            motivo = f"{motivo} (sem mensagem gerada — aguardando)"
        if step != "enviar_resposta":
            mensagem = None

        resultado_etapa = parsed.get("resultado_etapa")
        if resultado_etapa is not None:
            resultado_etapa = str(resultado_etapa).strip().lower() or None
        if step == "concluir_sucesso":
            resultado_etapa = "sucesso"
        elif step == "concluir_falha":
            resultado_etapa = "falha"
        elif step == "marcar_falha_retornar_pendente":
            if resultado_etapa not in ("ignorado", "inconclusivo"):
                resultado_etapa = "inconclusivo"
        else:
            resultado_etapa = None

        return AgentDecision(
            proximo_passo=step,
            motivo=motivo,
            mensagem_resposta=mensagem,
            resultado_etapa=resultado_etapa,
            source="openai",
            debug=debug,
        )
    except Exception as exc:
        _log.warning("OpenAI indisponível, heurística: %s", exc)
        analysis = analyze_conversation(messages, since=since)
        decision = _legacy_decision(analysis)
        decision.motivo = f"{decision.motivo} (fallback: {exc})"
        debug["modo"] = "heuristica_fallback"
        debug["erro_openai"] = str(exc)
        debug["analise"] = {
            "outcome": analysis.outcome.value,
            "motivo": analysis.reason,
            "mensagens_fornecedor": analysis.incoming_count,
        }
        decision.debug = debug
        return decision

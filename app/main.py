from contextlib import asynccontextmanager
import logging
import asyncpg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.config.config import obter_configuracao
from app.iam.rotas import ping_autenticado
from app.iam.rotas.dashboard_rotas import router as dashboard_auth_router
from app.mensageria.api.rotas import diagnostico_fornecedores, envio_mensagens, saude
from app.reenvio.api.rotas import (
    interno_n8n_router,
    interno_reenvio_router,
    webhook_email_router,
    webhook_sms_router,
)
from app.dashboard.api import dashboard_mutacoes_router, dashboard_router
from app.clique.api.rotas_clique import router as clique_router
from app.orquestracao.api.router import router as orquestracao_router
from app.reenvio.redis_app import fechar_cliente_redis, obter_cliente_redis
from app.templates.conexao import fechar_pool

_log = logging.getLogger(__name__)

_WEBHOOK_PREFIX = "/v1/webhooks/notificacao"
_MAX_LOG_BODY_WEBHOOK = 8000


def _configurar_logging() -> None:
    """Sem isto, loggers da app ficam no nível WARNING do root e INFO não aparece no terminal."""
    cfg = obter_configuracao()
    nivel = getattr(logging, cfg.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=nivel,
        format="%(levelname)s [%(name)s] %(message)s",
        force=True,
    )

@asynccontextmanager
async def lifespan(_app: FastAPI):
    _configurar_logging()
    await obter_cliente_redis()
    yield
    await fechar_pool()
    await fechar_cliente_redis()

app = FastAPI(
    title="API do sistema de notificações da ABC Advise",
    description="Infraestrutura inicial",
    lifespan=lifespan,
)

_cfg = obter_configuracao()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cfg.listar_origens_cors(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def _corpo_webhook_para_log(request: Request, exc: RequestValidationError) -> str | None:
    bruto = exc.body
    if bruto is None:
        try:
            bruto = await request.body()
        except Exception:
            return None
        if not bruto:
            return None
    if isinstance(bruto, bytes):
        texto = bruto.decode("utf-8", errors="replace")
    elif isinstance(bruto, str):
        texto = bruto
    else:
        texto = str(bruto)
    if len(texto) > _MAX_LOG_BODY_WEBHOOK:
        return f"{texto[:_MAX_LOG_BODY_WEBHOOK]}…(truncado)"
    return texto


@app.exception_handler(RequestValidationError)
async def _validacao_mensagens_email_400(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Payload inválido em POST /v1/mensagens/email (ex.: campo ``telefone_sms_fallback`` removido) → 400."""
    path = request.url.path.rstrip("/")
    if _WEBHOOK_PREFIX in path:
        _log.warning(
            "Webhook validação 422 path=%s detail=%s body=%s",
            path,
            exc.errors(),
            await _corpo_webhook_para_log(request, exc),
        )
    if path.endswith("/v1/mensagens/email"):
        return JSONResponse(status_code=400, content={"detail": exc.errors()})
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.exception_handler(asyncpg.exceptions.UndefinedTableError)
async def _sem_tabela_postgres(_request: Request, _exc: asyncpg.exceptions.UndefinedTableError) -> JSONResponse:
    """Evita 500 genérico quando o schema (ex. reenvio) ainda não foi aplicado na base."""
    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                "Postgres sem tabela necessária. Na pasta do projeto, com DATABASE_URL correto no ambiente, "
                "aplique o schema Postgres no ambiente de implantação (migrações / pipeline)."
            ),
        },
    )


app.include_router(saude.router, tags=["saúde"])
app.include_router(clique_router)
app.include_router(ping_autenticado.router, tags=["autenticação"])
app.include_router(envio_mensagens.router, tags=["envio"])
app.include_router(diagnostico_fornecedores.router, tags=["diagnóstico"])
app.include_router(webhook_email_router)
app.include_router(webhook_sms_router)
app.include_router(interno_reenvio_router)
app.include_router(interno_n8n_router)
app.include_router(orquestracao_router)
app.include_router(dashboard_auth_router)
app.include_router(dashboard_router)
app.include_router(dashboard_mutacoes_router)

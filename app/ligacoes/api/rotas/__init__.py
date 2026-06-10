from app.ligacoes.api.rotas.disparar import router_dashboard as ligacoes_dashboard_router
from app.ligacoes.api.rotas.disparar import router_disparar as ligacoes_disparar_router
from app.ligacoes.api.rotas.dispatch import router as calls_dispatch_router
from app.ligacoes.api.rotas.webhook_debug import router as webhook_vapi_debug_router
from app.ligacoes.api.rotas.webhook_voice import router as webhook_vapi_voice_router

__all__ = [
    "calls_dispatch_router",
    "ligacoes_dashboard_router",
    "ligacoes_disparar_router",
    "webhook_vapi_debug_router",
    "webhook_vapi_voice_router",
]

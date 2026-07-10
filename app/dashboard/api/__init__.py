from app.dashboard.api.rotas_dashboard import router as dashboard_router
from app.dashboard.api.rotas_envio_manual_dashboard import router as dashboard_envio_manual_router
from app.dashboard.api.rotas_mutacoes_dashboard import router as dashboard_mutacoes_router
from app.dashboard.api.rotas_variaveis_dashboard import router as dashboard_variaveis_router

__all__ = [
    "dashboard_router",
    "dashboard_mutacoes_router",
    "dashboard_envio_manual_router",
    "dashboard_variaveis_router",
]

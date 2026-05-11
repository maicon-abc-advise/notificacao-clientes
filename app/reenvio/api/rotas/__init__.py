from app.reenvio.api.rotas.interno_reenvio import router as interno_reenvio_router
from app.reenvio.api.rotas.interno_n8n import router as interno_n8n_router
from app.reenvio.api.rotas.webhook_email import router as webhook_email_router
from app.reenvio.api.rotas.webhook_sms import router as webhook_sms_router

__all__ = [
    "webhook_email_router",
    "webhook_sms_router",
    "interno_reenvio_router",
    "interno_n8n_router",
]

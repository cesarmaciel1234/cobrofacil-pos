"""Submódulo web del enlace Nube & CRM."""

from src.central_red_global.servidor.crm_salida.web.servidor_web import (
    detener_servidor_web,
    iniciar_servidor_web,
    obtener_url_web,
)

__all__ = ["iniciar_servidor_web", "detener_servidor_web", "obtener_url_web"]

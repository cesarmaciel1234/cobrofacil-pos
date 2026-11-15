"""Rama de enlace Nube & CRM. Desacoplada, bidireccional y resiliente."""

from src.central_red_global.servidor.crm_salida.motor.estado import estado_nube
from src.central_red_global.servidor.crm_salida.vigilante import apagar, pedir_vuelta, prender
from src.central_red_global.servidor.crm_salida.web.servidor_web import (
    detener_servidor_web,
    iniciar_servidor_web,
    obtener_url_web,
)

__all__ = [
    "prender",
    "apagar",
    "pedir_vuelta",
    "estado_nube",
    "iniciar_servidor_web",
    "detener_servidor_web",
    "obtener_url_web",
]

"""Motor de bajada y recepción de datos desde la Nube hacia la tienda local.

Este módulo prepara la infraestructura para recibir datos desde Render / Neon DB
(precios centralizados, clientes creados en la web, promociones, políticas de fiado)
sin bloquear las cajas registradoras ni alterar el funcionamiento local si se corta internet.

Principio de Inviolabilidad Local:
- Toda recepción se realiza primero en una cola o zona de staging.
- Si la descarga desde la nube se corta, el POS sigue operando con la última verdad local.
- No se realizan escrituras destructivas sin verificación previa.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from src.central_red_global.servidor.crm_salida.motor.estado import estado_nube

logger = logging.getLogger("crm_salida.bajada")


def consultar_novedades_nube(
    crm_url: str,
    api_key: str = "",
    empresa_id: str | None = None,
    sucursal_id: str | int | None = None,
    desde_timestamp: float | None = None,
    opener=None,
    timeout: int = 30,
) -> dict[str, Any]:
    """Consulta al CRM si existen novedades pendientes de descargar para esta sucursal."""
    crm_url = crm_url.rstrip("/")
    params: dict[str, Any] = {}
    if sucursal_id not in (None, ""):
        params["sucursal_id"] = str(sucursal_id)
    if desde_timestamp:
        params["desde"] = str(desde_timestamp)

    query = urllib.parse.urlencode(params)
    url = f"{crm_url}/api/pos/nube/novedades"
    if query:
        url = f"{url}?{query}"

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "CobroFacil-POS-Industrial/2026",
    }
    if api_key:
        headers["X-API-Key"] = api_key
    if empresa_id not in (None, ""):
        headers["X-Empresa-ID"] = str(empresa_id).strip()

    req = urllib.request.Request(url, method="GET", headers=headers)
    abridor = opener.open if opener is not None else urllib.request.urlopen

    try:
        with abridor(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            estado_nube.registrar_bajada("Novedades consultadas con éxito")
            return data
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            # El endpoint de novedades aún puede no estar habilitado en esta versión de Render
            logger.debug("Endpoint de bajada aún no publicado en Render (404).")
            return {"ok": True, "novedades": [], "pendiente_implementacion": True}
        detalle = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Error al consultar novedades: {detalle}") from exc
    except Exception as exc:
        logger.warning(f"CRM bajada  no se pudo consultar novedades: {exc}")
        return {"ok": False, "error": str(exc), "novedades": []}


def recibir_precios_centralizados(
    crm_url: str,
    api_key: str,
    empresa_id: str | None = None,
    sucursal_id: str | int | None = None,
    timeout: int = 40,
) -> list[dict]:
    """Descarga lista de precios modificados desde la nube para aplicar a góndola o caja."""
    res = consultar_novedades_nube(crm_url, api_key, empresa_id, sucursal_id, timeout=timeout)
    return res.get("precios", [])


def recibir_clientes_nube(
    crm_url: str,
    api_key: str,
    empresa_id: str | None = None,
    sucursal_id: str | int | None = None,
    timeout: int = 40,
) -> list[dict]:
    """Descarga clientes creados o modificados desde el CRM en la nube."""
    res = consultar_novedades_nube(crm_url, api_key, empresa_id, sucursal_id, timeout=timeout)
    return res.get("clientes", [])


def aplicar_novedades_en_staging(novedades: dict[str, Any], ruta_staging: str | None = None) -> bool:
    """Almacena novedades entrantes en una base de datos o archivo JSON de staging.

    De este modo, el motor principal o el operador pueden revisar y consolidar los cambios
    sin interrumpir transacciones activas de venta.
    """
    if not novedades:
        return True
    try:
        if not ruta_staging:
            base = os.path.dirname(os.path.abspath(__file__))
            raiz = os.path.abspath(os.path.join(base, "..", "..", "..", "..", ".."))
            ruta_staging = os.path.join(raiz, "locks", "novedades_nube_staging.json")

        os.makedirs(os.path.dirname(ruta_staging), exist_ok=True)
        with open(ruta_staging, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "timestamp": time.time(),
                    "recibido_en": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "contenido": novedades,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
        logger.info(f"CRM bajada  novedades guardadas en staging: {ruta_staging}")
        return True
    except Exception as exc:
        logger.error(f"CRM bajada  error guardando staging: {exc}")
        return False

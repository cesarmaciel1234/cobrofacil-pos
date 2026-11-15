"""Módulo de compatibilidad de subida al CRM. Este módulo no importa Qt.

Reexporta las funciones del motor hacia la raíz de la rama para garantizar
compatibilidad absoluta con tests anteriores y con el flag `--crm-cartera` de `main.py`.
"""

from __future__ import annotations

from src.central_red_global.servidor.crm_salida.motor.bajada import (
    aplicar_novedades_en_staging,
    consultar_novedades_nube,
    recibir_clientes_nube,
    recibir_precios_centralizados,
)
from src.central_red_global.servidor.crm_salida.motor.estado import GestorEstado, estado_nube
from src.central_red_global.servidor.crm_salida.motor.subida import (
    COLUMNAS_CLIENTES as COLUMNAS,
    enviar,
    entrar,
    huella,
    leer_base,
    leer_clientes,
    main,
    manifiesto,
    probar_conexion,
    resolver_empresa,
    subir_base,
)

__all__ = [
    "COLUMNAS",
    "enviar",
    "entrar",
    "huella",
    "leer_base",
    "leer_clientes",
    "main",
    "manifiesto",
    "probar_conexion",
    "resolver_empresa",
    "subir_base",
    "GestorEstado",
    "estado_nube",
    "consultar_novedades_nube",
    "recibir_precios_centralizados",
    "recibir_clientes_nube",
    "aplicar_novedades_en_staging",
]


if __name__ == "__main__":
    import sys

    sys.exit(main())

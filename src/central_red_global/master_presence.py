"""Presencia LAN de la PC Maestra (proceso Servidor de Tienda).

Tras un corte de luz / reinicio: el proceso `--server` deja la tienda visible
en la red sin abrir cajero.
"""

from src.logger import logger

_started = False


def es_pc_maestra_local() -> bool:
    """True si esta máquina debe hospedar el Servidor de Tienda.

    Solo lee config (no inicializa MariaDB) para poder decidir antes del spawn.
    """
    try:
        from src.config import config
        from src.base_de_datos.core.red_rol import leer_rol_red_desde_config

        data = {
            key: config.get(key)
            for key in ("db_host", "is_master", "carteleria_is_slave",
                        "preferred_master_ip", "carteleria_master_ip")
        }
        es_esclava, _ = leer_rol_red_desde_config(data)
        return not es_esclava
    except Exception as e:
        logger.error(f"master_presence: no se pudo evaluar rol maestra: {e}")
        return False


# Compat
_es_pc_maestra_local = es_pc_maestra_local


def ensure_master_lan_presence() -> bool:
    """Activa API/UDP discovery + NetworkEngine rol 'maestra' si corresponde.

    Idempotente. Preferible desde el proceso --server.
    """
    global _started

    if not es_pc_maestra_local():
        logger.info("Presencia Maestra: omitida (esta PC opera como esclava/remota).")
        return False

    try:
        from src.central_red_global.lan_server import init_lan_server

        init_lan_server()
    except Exception as e:
        logger.warning(f"Presencia Maestra: LAN server: {e}")

    try:
        from src.central_red_global.network_engine import (
            get_network_engine,
            init_network_engine,
        )

        eng = get_network_engine()
        if eng is None:
            init_network_engine("maestra")
            logger.info("Presencia Maestra: NetworkEngine iniciado (rol maestra).")
        else:
            try:
                eng.broadcast("HEARTBEAT", {"role": getattr(eng, "role", "maestra")})
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Presencia Maestra: NetworkEngine: {e}")
        return False

    if not _started:
        _started = True
        logger.info("Presencia Maestra LAN ACTIVA (servidor de tienda).")
    return True

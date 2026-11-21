"""Si la titular no contesta, la reserva pasa a ser la tienda con el espejo que ya tiene."""

from __future__ import annotations

import logging
import time

logger = logging.getLogger("oficio_servidor")

ESPERA_SEG = 300
_desde: float | None = None


def _guardar_puesto(config, cambios: dict) -> bool:
    anterior = config.data.copy()
    try:
        config.data.update(cambios)
        config.save()
        guardado = config._leer_json()
        if any(guardado.get(clave) != valor for clave, valor in cambios.items()):
            raise RuntimeError("La configuración guardada no coincide con el puesto solicitado")
        return True
    except Exception as e:
        config.data = anterior
        logger.error("pareja  no se pudo confirmar la configuración del puesto: %s", e)
        return False


def _titular_vive() -> bool:
    from src.central_red_global.servidor.pareja.buscar import _guardada, elegir, puerto_abierto

    host = _guardada()
    if host and host.lower() not in ("localhost", "127.0.0.1") and puerto_abierto(host):
        return True
    return bool(elegir())


def vigilar() -> None:
    """La reserva cuenta el silencio. A los cinco minutos levanta la tienda."""
    global _desde
    try:
        from src.central_red_global.servidor.pareja.reserva import soy

        if not soy():
            _desde = None
            return
    except Exception:
        return
    try:
        if _titular_vive():
            _desde = None
            return
    except Exception as e:
        logger.warning("pareja  no se pudo mirar la titular: %s", e)
        return
    if _desde is None:
        _desde = time.time()
        logger.info("pareja  la titular no contesta, la reserva espera cinco minutos")
        return
    if time.time() - _desde < ESPERA_SEG:
        return
    try:
        if not _promover():
            _desde = time.time()
    except Exception as e:
        _desde = time.time()
        logger.warning("pareja  no se pudo promover la reserva: %s", e)


def _promover() -> bool:
    from src.jefe.nodo_portable.espejo.copia import existe, ruta

    if not existe():
        logger.warning("pareja  no hay espejo para promover")
        return False
    try:
        from src.config import config

        if not str(config.get("store_id", "") or "").strip():
            logger.error("pareja  no se promueve: falta la identidad persistente de la tienda")
            return False
    except Exception as e:
        logger.error("pareja  no se promueve: no se pudo leer la identidad de tienda: %s", e)
        return False
    if _titular_vive():
        logger.info("pareja  la titular contesto, no me promuevo")
        return False
    logger.info("pareja  la titular murio, esta reserva pasa a ser la tienda")
    from src.services.mariadb_controller import mariadb_controller

    mariadb_controller.start_server()
    from src.central_red_global.servidor.pareja.buscar import puerto_abierto

    limite = time.time() + 40
    while time.time() < limite and not puerto_abierto("127.0.0.1"):
        time.sleep(1)
    if not puerto_abierto("127.0.0.1"):
        raise RuntimeError("MariaDB local no abrio")
    if _titular_vive():
        logger.info("pareja  la titular volvio mientras abria MariaDB, no me promuevo")
        try:
            mariadb_controller.stop_server()
        except Exception:
            pass
        return False

    from src.base_de_datos.database import db_manager

    db_manager.reconectar_mariadb("127.0.0.1")
    db_manager.is_master = True
    try:
        db_manager._create_tables()
        db_manager._migrate_db()
    except Exception as e:
        logger.warning("pareja  el esquema local quedo a medias: %s", e)
    motor = getattr(db_manager, "mariadb_engine", None)
    if motor is None:
        raise RuntimeError("no hay motor local")
    from src.base_de_datos.restaurar.aplicar.destino import Destino
    from src.base_de_datos.restaurar.aplicar.sumar import sumar

    destino = Destino("mariadb", host="127.0.0.1", conexion=motor._connect_kwargs())
    res = sumar(ruta(), destino)
    if "ventas" in (res.get("sin_lugar") or []):
        logger.warning("pareja  el espejo no entro en la tienda, sigo esclava")
        try:
            mariadb_controller.stop_server()
        except Exception:
            pass
        return False
    if _titular_vive():
        logger.info("pareja  la titular volvio mientras cargaba el espejo, no me promuevo")
        try:
            mariadb_controller.stop_server()
        except Exception:
            pass
        return False

    from src.config import config

    if not _guardar_puesto(config, {
        "is_master": True,
        "db_engine": "mariadb",
        "db_host": "127.0.0.1",
        "carteleria_is_slave": False,
        "preferred_master_ip": "",
        "carteleria_master_ip": "",
        "api_url": "http://127.0.0.1:8000",
    }):
        db_manager.is_master = False
        try:
            db_manager.reconectar_local()
        except Exception as e:
            logger.error("pareja  no se pudo volver al modo offline: %s", e)
        logger.error("pareja  promoción detenida; revisar MariaDB local y configuración")
        return False
    logger.info("pareja  espejo cargado, esta PC es la titular")
    from src.central_red_global.servidor.oficio.agente import retomar_oficio

    retomar_oficio()
    return True


def ceder_si_hay_otra() -> bool:
    """Si al prender ya hay una titular viva en la red, esta PC no abre una segunda tienda."""
    try:
        from src.central_red_global.master_presence import es_pc_maestra_local

        if not es_pc_maestra_local():
            return False
    except Exception:
        return False
    from src.base_de_datos.autoblindaje.quien.maestra import Quien
    from src.central_red_global.servidor.pareja.buscar import oir_anuncios, tiene_la_tienda
    from src.config import config

    identidad = str(config.get("store_id", "") or "").strip()
    if not identidad:
        logger.warning("pareja  no se puede ceder: falta la identidad de esta tienda")
        return False

    for aviso in oir_anuncios():
        if aviso.get("reserva"):
            continue
        if str(aviso.get("db_engine") or "").lower() not in ("", "mariadb"):
            continue
        ip = str(aviso.get("server_ip") or aviso.get("_desde") or "").strip()
        if not ip or Quien._es_esta_pc(ip):
            continue
        if str(aviso.get("store_id") or "").strip() != identidad:
            continue
        if not tiene_la_tienda(ip):
            continue

        if not _guardar_puesto(config, {
            "is_master": False,
            "db_host": ip,
            "preferred_master_ip": ip,
            "carteleria_master_ip": ip,
            "carteleria_is_slave": True,
            "api_url": f"http://{ip}:8000",
        }):
            return False
        logger.info("pareja  ya hay titular en %s, esta PC queda esclava", ip)
        try:
            from src.services.mariadb_controller import mariadb_controller

            mariadb_controller.stop_server()
        except Exception as e:
            logger.warning("pareja  MariaDB local sigue prendida: %s", e)
        return True
    return False

"""Módulo aparte del servidor. Si falla, la tienda sigue.

Por ahora la esclava también envía: trae los datos de la maestra
y con eso se trabaja en la web. Más adelante, SOLO_MAESTRA = True.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time

from src.central_red_global.servidor.crm_salida.proceso import comando, ruta_punpro

logger = logging.getLogger("crm_salida")

# Cada 10 min la tienda empuja lo nuevo de forma automática.
# Además, sondea cada 30s si la web/PWA solicitó sincronización inmediata.
PAUSA_PRIMERA_SEG = 30.0
PAUSA_VUELTA_SEG = 10 * 60.0
PAUSA_SONDEO_WEB_SEG = 30.0
MINIMO_ENTRE_ENVIOS_SEG = 60.0
TOPE_ENVIO_SEG = 2 * 60 * 60
SOLO_MAESTRA = False

_guardia = threading.Lock()
_hilo: threading.Thread | None = None
_parar = threading.Event()
_despertar = threading.Event()
_forzar_envio = False
_forzar_lock = threading.Lock()
_ultimo_aviso = ""


def leer_credenciales(origen: dict | None = None) -> dict | None:
    """URL, clave, empresa y sucursal. Sin eso no hay envío."""
    if origen is None:
        try:
            from src.config import config

            origen = {
                "crm_url": config.get("crm_url"),
                "crm_api_key": config.get("crm_api_key"),
                "crm_usuario": config.get("crm_usuario"),
                "crm_password": config.get("crm_password"),
                "crm_empresa": config.get("crm_empresa"),
                "crm_empresa_id": config.get("crm_empresa_id"),
                "crm_sucursal_id": config.get("crm_sucursal_id") or config.get("sucursal_id"),
                "crm_sucursal": config.get("crm_sucursal"),
            }
        except Exception:
            return None
    url = str(origen.get("crm_url") or "").strip().rstrip("/")
    clave = str(origen.get("crm_api_key") or "").strip()
    usuario = str(origen.get("crm_usuario") or "").strip()
    password = str(origen.get("crm_password") or "")
    empresa = str(origen.get("crm_empresa") or usuario).strip()
    empresa_id = str(origen.get("crm_empresa_id") or "").strip()
    sucursal_id = str(origen.get("crm_sucursal_id") or "").strip() or "1"
    sucursal = str(origen.get("crm_sucursal") or "").strip() or empresa
    if not url or not (clave or (usuario and password)) or not (empresa or empresa_id):
        return None
    return {
        "url": url,
        "clave": clave,
        "usuario": usuario,
        "password": password,
        "empresa": empresa,
        "empresa_id": empresa_id,
        "sucursal_id": sucursal_id,
        "sucursal": sucursal,
    }


def turno(rol: str, credenciales: dict | None, lanzar, *, solo_maestra: bool = SOLO_MAESTRA) -> str:
    """Una vuelta. Un fallo vuelve como texto y el servidor sigue."""
    if solo_maestra and rol != "maestra":
        return "esclava"
    if not credenciales:
        return "sin_datos"
    try:
        lanzar(credenciales)
    except Exception as exc:
        logger.exception("CRM  el envío falló y el servidor sigue")
        try:
            from src.central_red_global.servidor.crm_salida.motor.estado import estado_nube

            estado_nube.registrar_error(str(exc)[:160])
        except Exception:
            pass
        return "fallo"
    return "enviado"


def _marcar_origen() -> str:
    """Si la tienda usa MariaDB o el puerto local está abierto, lee MariaDB. Si no, según el rol."""
    try:
        from src.config import config
        db_engine = str(config.get("db_engine") or "").strip().lower()
    except Exception:
        db_engine = ""

    puerto_abierto = False
    try:
        from src.central_red_global.servidor.puerto import mariadb_port_open
        puerto_abierto = mariadb_port_open()
    except Exception:
        pass

    if db_engine == "mariadb" or puerto_abierto:
        origen = "mariadb"
    else:
        try:
            rol = _rol()
        except Exception:
            rol = "esclava"
        origen = "mariadb" if rol == "maestra" else "sqlite"
    os.environ["CRM_ORIGEN"] = origen
    return origen


def lanzar(credenciales: dict, forzar: bool = False) -> None:
    """Otro proceso lee la base y hace el POST. La clave no va en el comando."""
    from src.central_red_global.servidor.crm_salida.motor import huella, leer_clientes, manifiesto

    _marcar_origen()
    ruta_db = ruta_punpro()
    clientes = leer_clientes(ruta_db)
    marca = "|".join(
        [
            credenciales.get("url") or "",
            credenciales.get("empresa") or "",
            credenciales.get("empresa_id") or "",
            str(credenciales.get("sucursal_id") or ""),
            credenciales.get("sucursal") or "",
            manifiesto(ruta_db),
        ]
    )
    firma = huella(clientes, marca)
    carpeta = os.path.join(os.path.dirname(ruta_db) or ".", "locks")
    ruta_firma = os.path.join(carpeta, "crm_cartera_huella.txt")
    ruta_cuando = os.path.join(carpeta, "crm_cartera_cuando.txt")
    try:
        with open(ruta_firma, encoding="utf-8") as archivo:
            previa = archivo.read().strip()
    except OSError:
        previa = ""
    if previa == firma and not forzar:
        from src.central_red_global.servidor.crm_salida.motor.subida import (
            fotografiar,
            guardar_estado,
            ruta_estado,
        )

        if not os.path.isfile(ruta_estado(ruta_db)):
            guardar_estado(ruta_db, fotografiar(ruta_db))
            logger.info("CRM  la nube ya tiene este libro. Desde ahora solo salen los cambios.")
        else:
            logger.info("CRM  la base sigue igual. No se reenvía.")
        return
    try:
        with open(ruta_cuando, encoding="utf-8") as archivo:
            ultimo = float(archivo.read().strip() or 0)
    except (OSError, ValueError):
        ultimo = 0.0
    falta = MINIMO_ENTRE_ENVIOS_SEG - (time.time() - ultimo)
    if not forzar and ultimo and falta > 0:
        logger.info("CRM  hay cambios. El turno gratis abre en %s min.", int(falta // 60) + 1)
        return

    programa, args = comando()
    entorno = os.environ.copy()
    entorno["CRM_URL"] = credenciales["url"]
    entorno["CRM_API_KEY"] = credenciales.get("clave") or ""
    entorno["CRM_USER"] = credenciales.get("usuario") or ""
    entorno["CRM_PASSWORD"] = credenciales.get("password") or ""
    entorno["CRM_EMPRESA"] = credenciales.get("empresa") or ""
    entorno["CRM_EMPRESA_ID"] = credenciales.get("empresa_id") or ""
    entorno["CRM_SUCURSAL_ID"] = str(credenciales.get("sucursal_id") or "")
    entorno["CRM_SUCURSAL"] = credenciales.get("sucursal") or ""
    entorno["PUNPRO_DB"] = ruta_punpro()
    entorno["CRM_ORIGEN"] = os.environ.get("CRM_ORIGEN") or "sqlite"
    proc = subprocess.Popen(
        [programa, *args],
        env=entorno,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=os.path.dirname(ruta_punpro()) or None,
    )
    try:
        crudo, _ = proc.communicate(timeout=TOPE_ENVIO_SEG)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise RuntimeError("el envío tardó demasiado")
    texto = (crudo or b"").decode("utf-8", errors="replace")
    dato = {}
    for candidato in reversed(texto.splitlines()):
        candidato = candidato.strip()
        if candidato.startswith("{"):
            try:
                dato = json.loads(candidato)
            except json.JSONDecodeError:
                dato = {}
            break
    if proc.returncode != 0 or dato.get("ok") is False:
        detalle = str(dato.get("error") or texto or f"código {proc.returncode}")
        raise RuntimeError(detalle[:180])
    logger.info(
        "CRM  cartera enviada  %s leídos, %s nuevos, %s actualizados",
        dato.get("leidos", dato.get("total", "")),
        dato.get("creados", 0),
        dato.get("actualizados", 0),
    )
    try:
        from src.central_red_global.servidor.crm_salida.motor.estado import estado_nube

        t_subidos = dato.get("ventas_subidas", dato.get("ventas", 0))
        t_totales = dato.get("ventas_totales", dato.get("ventas", 0))
        progreso = dato.get("progreso_ventas") or (f"{t_subidos}/{t_totales}" if t_totales else f"{t_subidos}")
        estado_nube.registrar_exito(
            tablas=dato.get("tablas", 0),
            filas=dato.get("filas", dato.get("leidos", 0)),
            tickets=t_subidos,
            tickets_totales=t_totales,
            clientes=dato.get("clientes", dato.get("leidos", 0)),
            empresa=credenciales.get("empresa"),
            sucursal=credenciales.get("sucursal"),
            mensaje=f"Sincronizado con éxito — Ventas: {progreso} ({dato.get('tablas', 0)} tablas)",
        )
    except Exception:
        pass
    try:
        os.makedirs(os.path.dirname(ruta_firma), exist_ok=True)
        with open(ruta_firma, "w", encoding="utf-8") as archivo:
            archivo.write(firma)
        with open(ruta_cuando, "w", encoding="utf-8") as archivo:
            archivo.write(str(time.time()))
    except OSError:
        logger.warning("CRM  se envió, pero no pude anotar que la cartera ya está al día")


def _rol() -> str:
    from src.central_red_global.servidor.oficio.agente import oficio

    return oficio()


_fallos_consecutivos: int = 0
_ultimo_fallo: float = 0.0


def _vuelta(forzar: bool = False) -> None:
    global _ultimo_aviso, _fallos_consecutivos, _ultimo_fallo
    try:
        rol = _rol()
    except Exception as exc:
        if SOLO_MAESTRA:
            logger.error("CRM  no pude leer si esta PC es maestra: %s", exc)
            return
        rol = "esclava"
    credenciales = leer_credenciales()
    resultado = turno(rol, credenciales, lambda creds: lanzar(creds, forzar=forzar))
    if resultado == "esclava":
        if _ultimo_aviso != "esclava":
            logger.info("CRM  esta PC es esclava. No envía. La maestra manda el dato centralizado.")
            _ultimo_aviso = "esclava"
        return
    if resultado == "sin_datos":
        if _ultimo_aviso != "sin_datos":
            logger.info("CRM  falta el nombre de la empresa. El servidor sigue.")
            _ultimo_aviso = "sin_datos"
        return
    _ultimo_aviso = "maestra"
    if resultado == "enviado":
        _fallos_consecutivos = 0
    elif resultado == "fallo":
        _fallos_consecutivos += 1
        _ultimo_fallo = time.time()
        logger.error(
            "CRM  esta vuelta no salió (fallos consecutivos: %s). La próxima vuelve a intentar. El servidor sigue.",
            _fallos_consecutivos,
        )


def _consultar_peticion_web(credenciales: dict) -> bool:
    """Pregunta a la nube si desde la web o PWA pidieron sincronizar."""
    url = str(credenciales.get("url") or "").rstrip("/")
    if not url:
        return False
    try:
        import urllib.request
        sid = str(credenciales.get("sucursal_id") or "1")
        req = urllib.request.Request(
            f"{url}/api/pos/sync/pendiente?sucursal_id={sid}",
            headers={"User-Agent": "CobroFacil-POS-Industrial/2026"},
        )
        if credenciales.get("clave"):
            req.add_header("X-API-Key", credenciales["clave"])
        with urllib.request.urlopen(req, timeout=5) as resp:
            dato = json.loads(resp.read().decode("utf-8"))
            return bool(dato.get("pedir_envio"))
    except Exception:
        return False


def _confirmar_peticion_web(credenciales: dict) -> None:
    """Avisa a la nube que la petición de la web ya fue procesada."""
    url = str(credenciales.get("url") or "").rstrip("/")
    if not url:
        return
    try:
        import urllib.request
        sid = str(credenciales.get("sucursal_id") or "1")
        req = urllib.request.Request(
            f"{url}/api/pos/sync/confirmar?sucursal_id={sid}",
            headers={"User-Agent": "CobroFacil-POS-Industrial/2026"},
        )
        if credenciales.get("clave"):
            req.add_header("X-API-Key", credenciales["clave"])
        with urllib.request.urlopen(req, timeout=5) as resp:
            pass
    except Exception:
        pass


def _ciclo() -> None:
    logger.info("CRM  módulo aparte en marcha. Rutina cada 10 min y escucha activa de peticiones web.")
    ultimo_envio_rutina = time.time()

    # Primera vuelta rápida a los 30 seg
    if not _parar.wait(PAUSA_PRIMERA_SEG):
        try:
            _vuelta(forzar=False)
        except Exception as exc:
            logger.error("CRM  primera vuelta falló: %s", exc)
        ultimo_envio_rutina = time.time()

    while not _parar.is_set():
        despertado = _despertar.wait(PAUSA_SONDEO_WEB_SEG)
        _despertar.clear()
        if _parar.is_set():
            break

        global _forzar_envio
        con_fuerza = False
        with _forzar_lock:
            if _forzar_envio:
                con_fuerza = True
                _forzar_envio = False

        if not con_fuerza and not despertado:
            # Nadie llamó a pedir_vuelta() en los últimos 30 seg.
            creds = leer_credenciales()
            if creds and _consultar_peticion_web(creds):
                logger.info("CRM  la web/PWA solicitó sincronización. Despertando envío de inmediato.")
                con_fuerza = True
            elif time.time() - ultimo_envio_rutina >= PAUSA_VUELTA_SEG:
                # Rutina de 10 minutos cumplida
                con_fuerza = False
            else:
                continue

        try:
            _vuelta(forzar=con_fuerza)
            ultimo_envio_rutina = time.time()
            if con_fuerza:
                creds = leer_credenciales()
                if creds:
                    _confirmar_peticion_web(creds)
        except Exception as exc:
            logger.error("CRM  el módulo falló una vuelta y el servidor sigue: %s", exc)


def prender() -> None:
    """Arranca el hilo una sola vez. No toca MariaDB ni el espejo."""
    global _hilo
    with _guardia:
        if _hilo is not None and _hilo.is_alive():
            return
        _parar.clear()
        _hilo = threading.Thread(target=_ciclo, name="crm-salida", daemon=True)
        _hilo.start()


_timer_venta: threading.Timer | None = None
_timer_venta_lock = threading.Lock()


def notificar_venta(retraso_seg: float = 15.0) -> None:
    """Una caja acaba de cobrar una venta. Dispara una sincronización debounced.
    Si caen varias ventas seguidas (pico de caja), espera a que se calme 15 segundos
    para empaquetar todas las ventas juntas en un solo lote rápido.
    Aplica backoff adaptativo si la nube se encuentra temporalmente offline."""
    global _timer_venta, _fallos_consecutivos
    with _timer_venta_lock:
        if _timer_venta is not None:
            try:
                _timer_venta.cancel()
            except Exception:
                pass
        espera = retraso_seg
        if _fallos_consecutivos >= 3:
            # Backoff adaptativo si la nube está caída: no sobrecargar el sistema local
            espera = min(120.0, retraso_seg * (2 ** min(4, _fallos_consecutivos - 2)))
        _timer_venta = threading.Timer(espera, lambda: pedir_vuelta(forzar=True))
        _timer_venta.daemon = True
        _timer_venta.start()


def pedir_vuelta(forzar: bool = False) -> None:
    """La ventana guardó la empresa o solicitó sync manual."""
    global _forzar_envio, _fallos_consecutivos
    if forzar:
        with _forzar_lock:
            _forzar_envio = True
            _fallos_consecutivos = 0
    _despertar.set()


def apagar() -> None:
    _parar.set()
    _despertar.set()

"""Servidor web local embebido para la Mini Web de enlace con la Nube y CRM.

Corre en un hilo secundario independiente (`ThreadingHTTPServer`) en localhost.
Nunca interfiere con el servidor de la tienda ni con MariaDB ni con los cajeros.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import socket
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from src.central_red_global.servidor.crm_salida.motor.estado import estado_nube
from src.central_red_global.servidor.crm_salida.motor.subida import probar_conexion

logger = logging.getLogger("crm_salida.web")

_PUERTO_BASE = 8120
_MAX_INTENTOS_PUERTO = 10

_servidor_http: ThreadingHTTPServer | None = None
_hilo_servidor: threading.Thread | None = None
_candado_servidor = threading.Lock()
_puerto_activo: int = 0


def nombre_de_esta_pc() -> str:
    """El nombre de Windows de esta máquina. Es el nombre con el que se enlaza."""
    try:
        return str(socket.gethostname() or "").strip()
    except Exception:
        return ""


def sucursal_ya_anotada(sucursales: list[dict] | None, nombre: str) -> dict | None:
    """Si ese nombre ya está en la nube y tiene número, devuelve esa sucursal."""
    clave = str(nombre or "").strip().casefold()
    if not clave:
        return None
    for sucursal in sucursales or []:
        if str(sucursal.get("nombre") or "").strip().casefold() != clave:
            continue
        if sucursal.get("id") in (None, ""):
            continue
        return sucursal
    return None


def id_para_esta_pc(sucursales: list[dict] | None, pedido: str = "") -> tuple[str, str] | None:
    """Primero el nombre de la PC. Si no está, el nombre que escribieron, si ya tiene número."""
    pc = nombre_de_esta_pc()
    hallada = sucursal_ya_anotada(sucursales, pc) or sucursal_ya_anotada(sucursales, pedido)
    if not hallada:
        return None
    return str(hallada["id"]), str(hallada.get("nombre") or pedido or pc)


def _resolver_directorio_web() -> str:
    """Resuelve la ruta donde residen templates y static, compatible con desarrollo y PyInstaller."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base_mei = getattr(sys, "_MEIPASS")
        candidatos = [
            os.path.join(base_mei, "src", "central_red_global", "servidor", "crm_salida", "web"),
            os.path.join(base_mei, "crm_salida", "web"),
            os.path.join(base_mei, "web"),
            base_mei,
        ]
        for c in candidatos:
            if os.path.exists(os.path.join(c, "templates", "index.html")):
                return c
    return os.path.dirname(os.path.abspath(__file__))


def _buscar_puerto_libre(puerto_inicial: int = _PUERTO_BASE) -> int:
    for offset in range(_MAX_INTENTOS_PUERTO):
        puerto = puerto_inicial + offset
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", puerto))
            s.close()
            return puerto
        except OSError:
            continue
    raise RuntimeError(f"No se encontró ningún puerto libre entre {_PUERTO_BASE} y {_PUERTO_BASE + _MAX_INTENTOS_PUERTO}")


class MiniWebHandler(BaseHTTPRequestHandler):
    """Maneja las peticiones de la Mini Web y su API REST local."""

    def log_message(self, format: str, *args: Any) -> None:
        # Silenciar logs ruidosos de acceso HTTP en la consola estándar
        pass

    def _responder_json(self, dato: dict[str, Any], codigo: int = 200) -> None:
        cuerpo = json.dumps(dato, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(cuerpo)

    def _responder_archivo(self, ruta_completa: str, tipo_mime: str = "text/html; charset=utf-8") -> None:
        try:
            with open(ruta_completa, "rb") as f:
                contenido = f.read()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", tipo_mime)
            self.send_header("Content-Length", str(len(contenido)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(contenido)
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND, "Archivo no encontrado")

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        ruta = parsed.path

        directorio_actual = _resolver_directorio_web()

        if ruta == "/" or ruta == "/index.html":
            archivo = os.path.join(directorio_actual, "templates", "index.html")
            return self._responder_archivo(archivo, "text/html; charset=utf-8")

        if ruta.startswith("/static/"):
            relativa = ruta[len("/static/") :].replace("/", os.sep)
            archivo = os.path.join(directorio_actual, "static", relativa)
            tipo, _ = mimetypes.guess_type(archivo)
            return self._responder_archivo(archivo, tipo or "application/octet-stream")

        if ruta == "/api/estado":
            return self._manejar_api_estado()

        self.send_error(HTTPStatus.NOT_FOUND, "Ruta no encontrada")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        ruta = parsed.path

        largo = int(self.headers.get("Content-Length") or 0)
        cuerpo_bytes = self.rfile.read(largo) if largo > 0 else b"{}"
        try:
            cuerpo = json.loads(cuerpo_bytes.decode("utf-8")) if cuerpo_bytes else {}
        except Exception:
            return self._responder_json({"ok": False, "error": "JSON inválido en la solicitud"}, 400)

        if ruta == "/api/conectar":
            return self._manejar_api_conectar(cuerpo)
        elif ruta == "/api/reconectar":
            return self._manejar_api_reconectar()
        elif ruta == "/api/sincronizar":
            return self._manejar_api_sincronizar()
        elif ruta == "/api/desconectar":
            return self._manejar_api_desconectar()

        self.send_error(HTTPStatus.NOT_FOUND, "Endpoint no encontrado")

    def _manejar_api_estado(self) -> None:
        estado = estado_nube.obtener_estado()
        estado["nombre_pc"] = nombre_de_esta_pc()
        try:
            from src.config import config

            tiene_clave = bool(config.get("crm_password") or config.get("crm_api_key"))
            estado["tiene_clave_guardada"] = tiene_clave
        except Exception:
            estado["tiene_clave_guardada"] = False
        return self._responder_json(estado)

    def _manejar_api_conectar(self, datos: dict[str, Any]) -> None:
        url = str(datos.get("url") or "https://crm-frigorifico.onrender.com").strip().rstrip("/")
        empresa = str(datos.get("empresa") or datos.get("usuario") or "").strip()
        password = str(datos.get("password") or datos.get("clave") or "").strip()
        sucursal_id = str(datos.get("sucursal_id") or "").strip()
        sucursal = str(datos.get("sucursal") or "").strip() or nombre_de_esta_pc()

        # REGLA OBLIGATORIA: El nombre de la sucursal es obligatorio
        if not sucursal:
            estado_nube.registrar_error("El nombre de la sucursal es obligatorio.")
            return self._responder_json(
                {
                    "ok": False,
                    "error": "El nombre de la sucursal es obligatorio para identificar este nodo en la nube.",
                    "campo": "sucursal",
                },
                400,
            )

        if not url:
            return self._responder_json({"ok": False, "error": "Falta la dirección URL del CRM."}, 400)
        if not empresa:
            return self._responder_json({"ok": False, "error": "Falta el nombre de la empresa / usuario."}, 400)

        # Si no mandó password, revisar si ya había una guardada
        if not password:
            try:
                from src.config import config

                password = str(config.get("crm_password") or config.get("crm_api_key") or "").strip()
            except Exception:
                pass
            if not password:
                return self._responder_json({"ok": False, "error": "Debe ingresar la contraseña de la empresa."}, 400)

        # Guardar inmediatamente los datos ingresados en config local
        try:
            from src.config import config

            config.set("crm_url", url)
            config.set("crm_usuario", empresa)
            config.set("crm_empresa", empresa)
            if password:
                config.set("crm_password", password)
        except Exception as exc:
            logger.warning(f"Error guardando config local preliminar: {exc}")

        estado_nube.registrar_conectando(url, empresa, sucursal)

        # Probar autenticación contra la nube con timeout ampliado y consulta de sucursales
        ok, empresa_id, detalle, sucursales = probar_conexion(url, empresa, password)
        if not ok:
            if "incorrectos" in detalle.lower() or "no se pudo entrar" in detalle.lower():
                detalle_usuario = "Usuario o contraseña incorrectos en Render. Por favor reingrese la contraseña en el campo."
            elif "timed out" in detalle.lower() or "timeout" in detalle.lower():
                detalle_usuario = "Render está tardando en despertar el contenedor (Cold Start). Aguarde 10 segundos y vuelva a pulsar Reconectar."
            elif "502" in detalle or "503" in detalle or "504" in detalle:
                detalle_usuario = "Render está despertando el contenedor (Cold Start). Aguarde unos segundos y pulse Reconectar."
            else:
                detalle_usuario = detalle
            estado_nube.registrar_error(detalle_usuario)
            return self._responder_json(
                {
                    "ok": False,
                    "error": detalle_usuario,
                    "sugerencia": "Verifique las credenciales o si el servicio de Render está iniciando.",
                },
                400,
            )

        # El nombre de esta PC, si ya está en la nube, devuelve el número que ya tiene.
        nombre_sucursal = sucursal
        if sucursales:
            conocido = id_para_esta_pc(sucursales, sucursal)
            if not conocido:
                nombres = ", ".join(
                    f"{s.get('nombre')} (#{s.get('id')})"
                    for s in sucursales
                    if s.get("nombre") and s.get("id") not in (None, "")
                )
                pc = nombre_de_esta_pc() or sucursal
                detalle = (
                    f"Esta PC se llama {pc}. En la nube ese nombre no está"
                    + (f". Las que ya tienen número: {nombres}." if nombres else ".")
                    + " No enlacé con otro nombre."
                )
                estado_nube.registrar_error(detalle)
                return self._responder_json({"ok": False, "error": detalle, "sucursales": sucursales}, 400)
            sucursal_id, nombre_sucursal = conocido
        elif not sucursal_id:
            detalle = "No pude ver las sucursales de la nube, así que no asigné un número."
            estado_nube.registrar_error(detalle)
            return self._responder_json({"ok": False, "error": detalle}, 400)

        # Guardar en config local de la tienda
        try:
            from src.config import config

            config.set("crm_url", url)
            config.set("crm_usuario", empresa)
            config.set("crm_password", password)
            config.set("crm_empresa", empresa)
            if empresa_id:
                config.set("crm_empresa_id", empresa_id)
            config.set("crm_sucursal_id", sucursal_id)
            config.set("crm_sucursal", nombre_sucursal)
        except Exception as exc:
            logger.warning(f"Error guardando configuración CRM: {exc}")

        # Registrar éxito en el gestor de estado
        estado_nube.registrar_exito(
            empresa=empresa,
            sucursal=nombre_sucursal,
            mensaje=f"Enlazado correctamente a {url}. Empresa: {empresa}, Sucursal: #{sucursal_id} {nombre_sucursal}.",
        )

        # Despertar vigilante para sincronización inmediata
        try:
            from src.central_red_global.servidor.crm_salida.vigilante import pedir_vuelta

            pedir_vuelta()
        except Exception as exc:
            logger.warning(f"No se pudo despertar al vigilante: {exc}")

        return self._responder_json(
            {
                "ok": True,
                "mensaje": f"Conectado exitosamente con la Nube. Sucursal #{sucursal_id} {nombre_sucursal}.",
                "empresa_id": empresa_id,
                "sucursal_id": sucursal_id,
                "sucursal": nombre_sucursal,
                "sucursales": sucursales,
                "estado": estado_nube.obtener_estado(),
            }
        )

    def _manejar_api_reconectar(self) -> None:
        """Intenta reconectar con las credenciales almacenadas."""
        try:
            from src.config import config

            url = str(config.get("crm_url") or "https://crm-frigorifico.onrender.com").strip().rstrip("/")
            empresa = str(config.get("crm_empresa") or config.get("crm_usuario") or "").strip()
            password = str(config.get("crm_password") or config.get("crm_api_key") or "").strip()
            sucursal_id = str(config.get("crm_sucursal_id") or "1").strip()
            sucursal = str(config.get("crm_sucursal") or "").strip()
        except Exception:
            return self._responder_json({"ok": False, "error": "No hay credenciales previas para reconectar."}, 400)

        if not sucursal:
            return self._responder_json(
                {"ok": False, "error": "Falta el nombre de la sucursal (es obligatorio). Ingréselo en el formulario."},
                400,
            )

        estado_nube.registrar_conectando(url, empresa, sucursal)
        ok, empresa_id, detalle, sucursales = probar_conexion(url, empresa, password)
        if not ok:
            estado_nube.registrar_error(detalle)
            return self._responder_json({"ok": False, "error": detalle}, 400)

        conocido = id_para_esta_pc(sucursales, sucursal) if sucursales else None
        if conocido:
            sucursal_id, sucursal = conocido
            try:
                from src.config import config

                config.set("crm_sucursal_id", sucursal_id)
                config.set("crm_sucursal", sucursal)
            except Exception:
                pass

        estado_nube.registrar_exito(
            empresa=empresa,
            sucursal=sucursal,
            mensaje=f"Reconexión exitosa. Enlace activo con {url} (#{sucursal_id} {sucursal}).",
        )

        try:
            from src.central_red_global.servidor.crm_salida.vigilante import pedir_vuelta

            pedir_vuelta()
        except Exception:
            pass

        return self._responder_json(
            {"ok": True, "mensaje": "Reconectado con éxito", "estado": estado_nube.obtener_estado()}
        )

    def _manejar_api_sincronizar(self) -> None:
        """Fuerza una subida inmediata sin esperar el intervalo de 15 minutos."""
        try:
            from src.central_red_global.servidor.crm_salida.vigilante import pedir_vuelta

            pedir_vuelta()
            return self._responder_json(
                {"ok": True, "mensaje": "Ciclo de sincronización iniciado en segundo plano."}
            )
        except Exception as exc:
            return self._responder_json({"ok": False, "error": str(exc)}, 500)

    def _manejar_api_desconectar(self) -> None:
        try:
            from src.config import config

            config.set("crm_password", "")
        except Exception:
            pass
        estado_nube.registrar_error("Enlace desconectado por el usuario.")
        return self._responder_json({"ok": True, "mensaje": "Enlace desconectado."})


def iniciar_servidor_web() -> int:
    """Inicia el servidor web local si no está corriendo. Devuelve el puerto activo."""
    global _servidor_http, _hilo_servidor, _puerto_activo
    with _candado_servidor:
        if _servidor_http is not None:
            return _puerto_activo

        puerto = _buscar_puerto_libre(_PUERTO_BASE)
        servidor = ThreadingHTTPServer(("127.0.0.1", puerto), MiniWebHandler)
        hilo = threading.Thread(target=servidor.serve_forever, name="miniweb-crm", daemon=True)
        hilo.start()

        _servidor_http = servidor
        _hilo_servidor = hilo
        _puerto_activo = puerto
        logger.info(f"Mini Web CRM iniciada en http://127.0.0.1:{puerto}")
        return puerto


def obtener_url_web() -> str:
    puerto = iniciar_servidor_web()
    return f"http://127.0.0.1:{puerto}"


def detener_servidor_web() -> None:
    global _servidor_http, _hilo_servidor, _puerto_activo
    with _candado_servidor:
        if _servidor_http is not None:
            try:
                _servidor_http.shutdown()
                _servidor_http.server_close()
            except Exception:
                pass
            _servidor_http = None
            _hilo_servidor = None
            _puerto_activo = 0

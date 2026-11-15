"""Gestor de estado y telemetría del enlace Nube & CRM.

Totalmente desacoplado: guarda el estado en memoria y en un archivo JSON ligero
(locks/crm_estado.json). No bloquea base de datos ni afecta el cobro local.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any


class GestorEstado:
    """Gestiona el estado en vivo de la conexión y réplica con la nube."""

    _instancia: GestorEstado | None = None
    _candado = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._estado = {
            "conectado": False,
            "estado_texto": "desconectado",  # 'conectado', 'conectando', 'error', 'desconectado'
            "mensaje": "No se ha enlazado todavía con la nube.",
            "url": "https://crm-frigorifico.onrender.com",
            "empresa": "",
            "empresa_id": "",
            "sucursal_id": "1",
            "sucursal": "",
            "ultimo_envio": None,
            "ultima_bajada": None,
            "filas_totales": 0,
            "tablas_totales": 0,
            "ultimo_error": None,
            "reintentos": 0,
            "resiliencia": "Modo Autónomo Activo — La tienda opera 100% offline si falla internet",
            "soporta_bajada": True,
            "actualizado_en": time.time(),
        }
        self._cargar_disco()

    @classmethod
    def get(cls) -> GestorEstado:
        with cls._candado:
            if cls._instancia is None:
                cls._instancia = cls()
            return cls._instancia

    def _ruta_archivo(self) -> str:
        base = os.path.dirname(os.path.abspath(__file__))
        # Buscar carpeta locks en la raíz del proyecto o servidor
        raiz = os.path.abspath(os.path.join(base, "..", "..", "..", "..", ".."))
        locks = os.path.join(raiz, "locks")
        os.makedirs(locks, exist_ok=True)
        return os.path.join(locks, "crm_estado.json")

    def _cargar_disco(self) -> None:
        try:
            ruta = self._ruta_archivo()
            if os.path.isfile(ruta):
                with open(ruta, "r", encoding="utf-8") as f:
                    datos = json.load(f)
                    if isinstance(datos, dict):
                        self._estado.update(datos)
        except Exception:
            pass

    def _guardar_disco(self) -> None:
        try:
            ruta = self._ruta_archivo()
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump(self._estado, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def obtener_estado(self) -> dict[str, Any]:
        with self._lock:
            # Sincronizar datos básicos desde config si están disponibles
            try:
                from src.config import config

                url = str(config.get("crm_url") or "").strip()
                empresa = str(config.get("crm_empresa") or config.get("crm_usuario") or "").strip()
                sucursal = str(config.get("crm_sucursal") or "").strip()
                sucursal_id = str(config.get("crm_sucursal_id") or "1").strip()
                if url:
                    self._estado["url"] = url
                if empresa:
                    self._estado["empresa"] = empresa
                if sucursal:
                    self._estado["sucursal"] = sucursal
                if sucursal_id:
                    self._estado["sucursal_id"] = sucursal_id
            except Exception:
                pass
            return dict(self._estado)

    def registrar_sucursal_local(self, sucursal_id: str, sucursal: str) -> None:
        """Actualiza y persiste la sucursal localmente sin requerir conexión a internet."""
        with self._lock:
            if sucursal_id:
                self._estado["sucursal_id"] = str(sucursal_id).strip()
            if sucursal:
                self._estado["sucursal"] = str(sucursal).strip()
            self._estado["actualizado_en"] = time.time()
            self._guardar_disco()

    def registrar_conectando(self, url: str, empresa: str, sucursal: str) -> None:
        with self._lock:
            self._estado["conectado"] = False
            self._estado["estado_texto"] = "conectando"
            self._estado["mensaje"] = f"Conectando a {url}..."
            self._estado["url"] = url
            self._estado["empresa"] = empresa
            self._estado["sucursal"] = sucursal
            self._estado["actualizado_en"] = time.time()
            self._guardar_disco()

    def registrar_exito(
        self,
        *,
        tablas: int | None = None,
        filas: int | None = None,
        empresa: str | None = None,
        sucursal: str | None = None,
        mensaje: str = "Conectado y sincronizado con éxito",
    ) -> None:
        with self._lock:
            self._estado["conectado"] = True
            self._estado["estado_texto"] = "conectado"
            self._estado["mensaje"] = mensaje
            if empresa:
                self._estado["empresa"] = empresa
            if sucursal:
                self._estado["sucursal"] = sucursal
            if tablas is not None or filas is not None:
                self._estado["ultimo_envio"] = time.strftime("%Y-%m-%d %H:%M:%S")
                self._estado["filas_totales"] = filas or 0
                self._estado["tablas_totales"] = tablas or 0
            self._estado["ultimo_error"] = None
            self._estado["actualizado_en"] = time.time()
            self._guardar_disco()

    def registrar_error(self, error: str) -> None:
        with self._lock:
            self._estado["conectado"] = False
            self._estado["estado_texto"] = "error"
            self._estado["ultimo_error"] = error
            self._estado["mensaje"] = f"Error de conexión: {error}"
            self._estado["actualizado_en"] = time.time()
            self._guardar_disco()

    def registrar_bajada(self, detalle: str) -> None:
        with self._lock:
            self._estado["ultima_bajada"] = time.strftime("%Y-%m-%d %H:%M:%S")
            self._guardar_disco()


estado_nube = GestorEstado.get()

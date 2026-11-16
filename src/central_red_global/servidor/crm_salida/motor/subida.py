"""Motor de subida y transporte al CRM en la Nube (Render + Neon DB).

Aislado y desacoplado:
- La maestra lee MariaDB en solo lectura. La esclava lee su SQLite.
- No escribe en la caja ni en MariaDB.
- Filtra claves y secretos antes de enviar a la nube.
- Maneja cold start de Render (reintentos 502/503/504).
- La semana más nueva sale primero. Cada semana viaja de a 150 filas.
"""

from __future__ import annotations

import hashlib
import http.cookiejar
import json
import logging
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

from src.central_red_global.servidor.crm_salida.motor.estado import estado_nube

logger = logging.getLogger("crm_salida.subida")

_TABLA = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# La pantalla abre por ventas. Esas tablas salen antes que el resto del libro.
_PRIMERO = (
    "ventas",
    "detalles_ventas",
    "ventas_items",
    "clientes",
    "cuenta_corriente",
    "productos",
    "configuracion",
)


def _ordenar_tablas(nombres: list[str]) -> list[str]:
    puesto = {nombre: i for i, nombre in enumerate(_PRIMERO)}
    return sorted(
        nombres,
        key=lambda nombre: (nombre not in puesto, puesto.get(nombre, 0), nombre),
    )


def _indice_fecha(columnas) -> int | None:
    bajos = [str(col).lower() for col in columnas]
    for nombre in ("fecha", "fecha_hora", "fecha_venta", "fecha_cierre", "created_at"):
        if nombre in bajos:
            return bajos.index(nombre)
    return None


def _lunes(valor) -> str:
    texto = str(valor or "").strip()[:10]
    if len(texto) != 10 or texto[4] != "-" or texto[7] != "-":
        return ""
    try:
        dia = date.fromisoformat(texto)
    except ValueError:
        return ""
    lunes = dia.fromordinal(dia.toordinal() - dia.weekday())
    return lunes.isoformat()


def _mapa_semanas(columnas, filas) -> dict[str, str]:
    bajos = [str(col).lower() for col in columnas]
    if "id" not in bajos or "fecha" not in bajos:
        return {}
    idx_id = bajos.index("id")
    idx_fecha = bajos.index("fecha")
    mapa = {}
    for fila in filas:
        lunes = _lunes(fila[idx_fecha])
        if lunes:
            mapa[str(fila[idx_id])] = lunes
    return mapa


def _lotes_semana(columnas, filas, semanas_venta: dict | None = None) -> list[list]:
    """Agrupa por semana, de la más nueva a la más vieja. Sin fecha, un solo lote."""
    idx_fecha = _indice_fecha(columnas)
    bajos = [str(col).lower() for col in columnas]
    idx_venta = bajos.index("id_venta") if "id_venta" in bajos else None
    if idx_fecha is None and idx_venta is None:
        return [list(filas)]
    grupos: dict[str, list] = {}
    sin_fecha = []
    for fila in filas:
        lunes = ""
        if idx_fecha is not None:
            lunes = _lunes(fila[idx_fecha])
        elif semanas_venta and idx_venta is not None:
            lunes = semanas_venta.get(str(fila[idx_venta]), "")
        if not lunes:
            sin_fecha.append(fila)
            continue
        grupos.setdefault(lunes, []).append(fila)
    lotes = [grupos[clave] for clave in sorted(grupos, reverse=True)]
    if sin_fecha:
        lotes.append(sin_fecha)
    return lotes or [[]]


def _bloques(columnas, filas, semanas_venta: dict | None = None) -> list[list]:
    bloques = []
    for lote in _lotes_semana(columnas, filas, semanas_venta):
        if not lote:
            continue
        for inicio in range(0, len(lote), _TAMANO_PARTE):
            bloques.append(lote[inicio : inicio + _TAMANO_PARTE])
    return bloques or [[]]
_SECRETOS = ("password", "passwd", "token", "secret", "api_key", "access_token", "refresh_token")
_TAMANO_PARTE = 150

COLUMNAS_CLIENTES = (
    "id",
    "uid",
    "nombre",
    "telefono",
    "dni",
    "direccion",
    "limite_credito",
    "deuda_actual",
    "tipo_cliente",
    "estado_cuenta",
    "actualizado_en",
    "plazo_dias",
)


def leer_clientes(ruta_db: str) -> list[dict]:
    """Lee clientes. En la maestra salen de MariaDB; en la esclava, de su SQLite."""
    if os.environ.get("CRM_ORIGEN") == "mariadb":
        return _clientes_mariadb()
    conn = sqlite3.connect(f"file:{ruta_db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        tablas = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "clientes" not in tablas:
            raise RuntimeError(f"punpro.db no tiene clientes: {ruta_db}")
        existentes = {row[1] for row in conn.execute("PRAGMA table_info(clientes)")}
        cols = [c for c in COLUMNAS_CLIENTES if c in existentes]
        if "nombre" not in cols:
            raise RuntimeError("La tabla clientes no tiene nombre")
        filas = conn.execute(
            f"SELECT {', '.join(cols)} FROM clientes ORDER BY nombre"
        ).fetchall()
    finally:
        conn.close()

    clientes = []
    for fila in filas:
        item = {col: fila[col] for col in cols}
        nombre = str(item.get("nombre") or "").strip()
        if not nombre:
            continue
        item["nombre"] = nombre
        for clave, valor in list(item.items()):
            if isinstance(valor, bytes):
                item[clave] = valor.decode("utf-8", errors="replace")
        clientes.append(item)
    return clientes


def huella(clientes: list[dict], marca: str = "") -> str:
    """Firma del lote. Si no cambia, no hace falta volver a mandarlo."""
    crudo = json.dumps(
        {"marca": marca, "clientes": clientes},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()


def manifiesto(ruta_db: str) -> str:
    """Firma de toda la base. Cambia si cambia cualquier tabla."""
    trozos = []
    for tabla, columnas, filas in _fuente(ruta_db):
        trozos.append(
            (
                tabla,
                json.dumps(
                    {"tabla": tabla, "columnas": columnas, "filas": filas},
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                ),
            )
        )
    trozos.sort(key=lambda item: item[0])
    return hashlib.sha256("\n".join(texto for _, texto in trozos).encode("utf-8")).hexdigest()


def _fuente(ruta_db: str):
    if os.environ.get("CRM_ORIGEN") == "mariadb":
        return leer_mariadb()
    return leer_base(ruta_db)


def _conexion_mariadb():
    """Lectura de la maestra. Si MariaDB no está, no se usa la copia SQLite."""
    import pymysql
    from src.base_de_datos.database import db_manager

    if getattr(db_manager, "db_engine_type", "") != "mariadb" or getattr(db_manager, "_forced_local_offline", False):
        raise RuntimeError("La maestra no tiene MariaDB abierta")
    motor = getattr(db_manager, "mariadb_engine", None)
    if motor is None:
        raise RuntimeError("La maestra no tiene MariaDB abierta")
    datos = motor._connect_kwargs()
    datos.update(connect_timeout=5, read_timeout=120, write_timeout=10)
    conn = pymysql.connect(**datos)
    try:
        with conn.cursor() as cur:
            cur.execute("SET SESSION TRANSACTION READ ONLY")
    except Exception:
        pass
    return conn


def _clientes_mariadb() -> list[dict]:
    conn = _conexion_mariadb()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'clientes' ORDER BY ORDINAL_POSITION"
            )
            existentes = {row[0] for row in cur.fetchall()}
        cols = [c for c in COLUMNAS_CLIENTES if c in existentes]
        if "nombre" not in cols:
            raise RuntimeError("La tabla clientes de MariaDB no tiene nombre")
        with conn.cursor() as cur:
            cur.execute(f"SELECT {', '.join('`'+c+'`' for c in cols)} FROM `clientes` ORDER BY `nombre`")
            crudas = cur.fetchall()
    finally:
        conn.close()
    clientes = []
    for cruda in crudas:
        item = {col: _plano(valor) for col, valor in zip(cols, cruda)}
        nombre = str(item.get("nombre") or "").strip()
        if not nombre:
            continue
        item["nombre"] = nombre
        clientes.append(item)
    return clientes


def leer_mariadb():
    """Tablas de la maestra, solo lectura. Misma forma que la copia SQLite."""
    conn = _conexion_mariadb()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT TABLE_NAME FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_NAME"
            )
            nombres = _ordenar_tablas([row[0] for row in cur.fetchall()])
        for nombre in nombres:
            if not _TABLA.match(str(nombre)):
                continue
            with conn.cursor() as cur:
                cur.execute(f"SELECT * FROM `{nombre}`")
                columnas = [d[0] for d in cur.description] if cur.description else []
                crudas = cur.fetchall()
            yield nombre, columnas, _limpiar_filas(nombre, columnas, crudas)
    finally:
        conn.close()


def _plano(valor):
    if isinstance(valor, bytes):
        return valor.decode("utf-8", errors="replace")
    if hasattr(valor, "isoformat"):
        return valor.isoformat(sep=" ")
    try:
        from decimal import Decimal

        if isinstance(valor, Decimal):
            return format(valor, "f")
    except Exception:
        pass
    return valor


def _limpiar_filas(nombre, columnas, crudas):
    idx_clave = next(
        (i for i, col in enumerate(columnas) if col.lower() in ("clave", "key", "nombre")),
        None,
    )
    idx_valor = next(
        (i for i, col in enumerate(columnas) if col.lower() in ("valor", "value")),
        None,
    )
    filas = []
    for cruda in crudas:
        fila = [_plano(valor) for valor in cruda]
        for i, col in enumerate(columnas):
            if _clave_secreta(col):
                fila[i] = None
        if (
            idx_clave is not None
            and idx_valor is not None
            and _clave_secreta(str(fila[idx_clave] or ""))
        ):
            fila[idx_valor] = None
        filas.append(fila)
    if nombre == "configuracion" and idx_clave is not None and idx_valor is not None:
        presentes = {str(fila[idx_clave]) for fila in filas}
        try:
            from src.config import config

            politica = {
                "fiado_mantenimiento_pct": config.get("fiado_mantenimiento_pct", 5),
                "fiado_apalancamiento_pct": config.get("fiado_apalancamiento_pct", 5),
                "fiado_plazo_dias": config.get("fiado_plazo_dias", 30),
            }
        except Exception:
            politica = {
                "fiado_mantenimiento_pct": 5,
                "fiado_apalancamiento_pct": 5,
                "fiado_plazo_dias": 30,
            }
        for clave, valor in politica.items():
            if clave in presentes:
                continue
            extra = [None] * len(columnas)
            extra[idx_clave] = clave
            extra[idx_valor] = valor
            filas.append(extra)
    return filas


def _clave_secreta(texto: str) -> bool:
    n = texto.lower()
    return any(marca in n for marca in _SECRETOS)


def leer_base(ruta_db: str):
    """Generador de todas las tablas en modo solo lectura. Filtra contraseñas."""
    conn = sqlite3.connect(f"file:{ruta_db}?mode=ro", uri=True)
    try:
        nombres = _ordenar_tablas(
            [
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                )
            ]
        )
        for nombre in nombres:
            if not _TABLA.match(nombre):
                continue
            columnas = [col[1] for col in conn.execute(f'PRAGMA table_info("{nombre}")')]
            crudas = conn.execute(f'SELECT * FROM "{nombre}"').fetchall()
            yield nombre, columnas, _limpiar_filas(nombre, columnas, crudas)
    finally:
        conn.close()


def _pedir(abridor, req, timeout: int, intentos: int = 4):
    """Reintenta si Render corta la conexión o se encuentra en Cold Start."""
    ultimo = None
    for numero in range(intentos):
        try:
            with abridor(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detalle = exc.read().decode("utf-8", errors="replace")
            if exc.code in (502, 503, 504) and numero + 1 < intentos:
                time.sleep(3 * (numero + 1))
                continue
            raise RuntimeError(detalle[:180]) from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            ultimo = exc
            if numero + 1 < intentos:
                time.sleep(3 * (numero + 1))
                continue
            raise
    raise ultimo


def ruta_estado(ruta_db: str) -> str:
    nombre = "crm_filas_estado_mariadb.json" if os.environ.get("CRM_ORIGEN") == "mariadb" else "crm_filas_estado.json"
    return os.path.join(os.path.dirname(ruta_db) or ".", "locks", nombre)


def _huella_fila(fila) -> str:
    crudo = json.dumps(fila, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()


def _indice_id(columnas) -> int | None:
    for i, col in enumerate(columnas):
        if str(col).lower() == "id":
            return i
    return None


def fotografiar(ruta_db: str) -> dict:
    """Anota cada fila que ya está en la nube para no volver a mandarla."""
    estado = {}
    for tabla, columnas, filas in _fuente(ruta_db):
        idx = _indice_id(columnas)
        if idx is None:
            estado[tabla] = {"modo": "tabla", "huella": _huella_fila(filas)}
        else:
            estado[tabla] = {
                "modo": "id",
                "filas": {str(fila[idx]): _huella_fila(fila) for fila in filas},
            }
    return estado


def guardar_estado(ruta_db: str, estado: dict) -> None:
    ruta = ruta_estado(ruta_db)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as archivo:
        json.dump(estado, archivo, ensure_ascii=False)


def leer_estado(ruta_db: str) -> dict:
    try:
        with open(ruta_estado(ruta_db), encoding="utf-8") as archivo:
            dato = json.load(archivo)
    except (OSError, json.JSONDecodeError):
        return {}
    return dato if isinstance(dato, dict) else {}


def subir_base(
    crm_url: str,
    api_key: str,
    ruta_db: str,
    empresa_id: str | None = None,
    sucursal_id: str | int | None = None,
    sucursal: str | None = None,
    opener=None,
    timeout: int = 120,
    reentrar=None,
) -> dict:
    """Sube solo las filas que cambiaron. La primera vez anota el libro que ya está en la nube."""
    abridor = opener.open if opener is not None else urllib.request.urlopen
    estado = leer_estado(ruta_db)
    nuevo = dict(estado)
    tablas_ok = 0
    filas = 0
    errores = []
    hubo = False
    semanas_venta: dict[str, str] = {}
    for tabla, columnas, todas in _fuente(ruta_db):
        if tabla == "ventas":
            semanas_venta = _mapa_semanas(columnas, todas)
        idx = _indice_id(columnas)
        previa = estado.get(tabla) or {}
        if idx is None:
            huella_tabla = _huella_fila(todas)
            nuevo[tabla] = {"modo": "tabla", "huella": huella_tabla}
            if previa.get("huella") == huella_tabla:
                continue
            bajas = []
            modo = "reemplazo"
        else:
            actuales = {}
            cambiadas = []
            for fila in todas:
                clave = str(fila[idx])
                firma = _huella_fila(fila)
                actuales[clave] = firma
                if (previa.get("filas") or {}).get(clave) != firma:
                    cambiadas.append(fila)
            bajas = [clave for clave in (previa.get("filas") or {}) if clave not in actuales]
            nuevo[tabla] = {"modo": "id", "filas": actuales}
            if not cambiadas and not bajas:
                continue
            todas = cambiadas
            modo = "delta"
        hubo = True
        guia = semanas_venta if _indice_fecha(columnas) is None else None
        partes = _bloques(columnas, todas, guia)
        fallo = None
        for numero, bloque in enumerate(partes, start=1):
            cuerpo = {
                "tabla": tabla,
                "columnas": columnas,
                "filas": bloque,
                "parte": numero,
                "partes": len(partes),
                "modo": modo,
            }
            if modo == "delta" and numero == len(partes):
                cuerpo["bajas"] = bajas
            if sucursal_id not in (None, ""):
                cuerpo["sucursal_id"] = int(sucursal_id)
                cuerpo["branch_id"] = int(sucursal_id)
            if empresa_id not in (None, ""):
                cuerpo["tenant_id"] = str(empresa_id).strip()
            if sucursal:
                cuerpo["sucursal"] = sucursal
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["X-API-Key"] = api_key
            if empresa_id not in (None, ""):
                headers["X-Empresa-ID"] = str(empresa_id).strip()
            req = urllib.request.Request(
                f"{crm_url.rstrip('/')}/api/pos/base/tabla",
                data=json.dumps(cuerpo, default=str).encode("utf-8"),
                method="POST",
                headers=headers,
            )
            reintentos_sesion = 0
            while True:
                try:
                    dato = _pedir(abridor, req, timeout)
                    break
                except Exception as exc:
                    texto = str(exc)
                    sesion_vencida = "No autorizado" in texto or "expirada" in texto.lower()
                    if reentrar is not None and sesion_vencida and reintentos_sesion < 2:
                        reintentos_sesion += 1
                        sesion = reentrar()
                        if sesion is not None:
                            abridor = sesion.open if hasattr(sesion, "open") else sesion
                        time.sleep(2)
                        continue
                    fallo = {"tabla": tabla, "parte": numero, "error": texto[:180]}
                    break
            if fallo:
                break
            if not dato.get("ok"):
                fallo = {"tabla": tabla, "parte": numero, "error": str(dato.get("error") or dato)}
                break
        if fallo:
            errores.append(fallo)
            continue
        tablas_ok += 1
        filas += len(todas) + len(bajas)
    if not errores:
        guardar_estado(ruta_db, nuevo)
    return {"tablas": tablas_ok, "filas": filas, "errores": errores, "delta": True}


def resolver_empresa(crm_url: str, api_key: str, nombre: str, timeout: int = 20) -> str:
    """Traduce el nombre comercial de la empresa en su ID numérico en la nube."""
    consulta = urllib.parse.urlencode({"nombre": nombre})
    req = urllib.request.Request(
        f"{crm_url.rstrip('/')}/api/pos/empresas/resolver?{consulta}",
        method="GET",
        headers={"X-API-Key": api_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            dato = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detalle = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"No encontré la empresa {nombre}: {detalle}") from exc
    empresa_id = str(dato.get("id") or "").strip()
    if not empresa_id:
        raise RuntimeError(f"El CRM no devolvió el número de {nombre}")
    return empresa_id


def entrar(crm_url: str, usuario: str, password: str, timeout: int = 60):
    """Inicia sesión contra el CRM en la nube y devuelve la sesión y el ID de empresa."""
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    cuerpo = json.dumps({"username": usuario, "password": password}).encode("utf-8")
    req = urllib.request.Request(
        f"{crm_url.rstrip('/')}/auth/login",
        data=cuerpo,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with opener.open(req, timeout=timeout) as resp:
            dato = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detalle = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"No se pudo entrar: {detalle}") from exc
    if not dato.get("ok"):
        raise RuntimeError(str(dato.get("error") or "No se pudo entrar"))
    user = dato.get("user") or {}
    return opener, str(user.get("empresa_id") or "").strip()


def obtener_sucursales_nube(crm_url: str, opener=None, timeout: int = 30) -> list[dict]:
    """Consulta la lista de sucursales registradas en el CRM para la empresa."""
    abridor = opener.open if opener is not None else urllib.request.urlopen
    try:
        url = f"{crm_url.rstrip('/')}/api/pos/sucursales"
        req = urllib.request.Request(url, method="GET")
        with abridor(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict):
                return data.get("sucursales", [])
    except Exception:
        pass
    return []


def probar_conexion(
    crm_url: str,
    usuario: str,
    password: str,
    api_key: str = "",
    timeout: int = 60,
    intentos: int = 2,
) -> tuple[bool, str, str, list[dict]]:
    """Prueba la conexión al CRM con reintentos para soportar Cold Starts de Render.

    Retorna (ok, empresa_id, mensaje_o_error, lista_sucursales).
    """
    crm_url = crm_url.strip().rstrip("/")
    if not crm_url:
        return False, "", "Falta la URL de la nube.", []
    ultimo_error = ""
    for num in range(intentos):
        try:
            if usuario and password:
                opener, empresa_id = entrar(crm_url, usuario, password, timeout=timeout)
                sucursales = obtener_sucursales_nube(crm_url, opener, timeout=timeout)
                return True, empresa_id, "Credenciales validadas con éxito.", sucursales
            elif api_key:
                empresa_id = resolver_empresa(crm_url, api_key, usuario or "empresa", timeout=timeout)
                return True, empresa_id, "API Key validada con éxito.", []
            else:
                return False, "", "Debe ingresar usuario y contraseña o API Key.", []
        except Exception as exc:
            ultimo_error = str(exc)
            if (
                "timed out" in ultimo_error.lower()
                or any(code in ultimo_error for code in ("502", "503", "504"))
            ) and num + 1 < intentos:
                time.sleep(3)
                continue
            break
    return False, "", ultimo_error, []


def enviar(
    crm_url: str,
    api_key: str,
    clientes: list[dict],
    timeout: int = 120,
    empresa_id: str | None = None,
    sucursal_id: str | int | None = None,
    sucursal: str | None = None,
    opener=None,
) -> dict:
    """Envía el lote de clientes a /api/pos/clientes/lote."""
    cuerpo_obj: dict = {"clientes": clientes}
    if sucursal_id not in (None, ""):
        cuerpo_obj["sucursal_id"] = int(sucursal_id)
    if sucursal:
        cuerpo_obj["sucursal"] = sucursal
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
    if empresa_id not in (None, ""):
        headers["X-Empresa-ID"] = str(empresa_id).strip()
    cuerpo = json.dumps(cuerpo_obj).encode("utf-8")
    req = urllib.request.Request(
        f"{crm_url.rstrip('/')}/api/pos/clientes/lote",
        data=cuerpo,
        method="POST",
        headers=headers,
    )
    try:
        abridor = opener.open if opener is not None else urllib.request.urlopen
        return _pedir(abridor, req, timeout)
    except RuntimeError as exc:
        raise RuntimeError(f"El CRM respondió {exc}") from exc


def main() -> int:
    """Punto de entrada de subproceso (llamado con --crm-cartera)."""
    url = (os.environ.get("CRM_URL") or "").strip().rstrip("/")
    clave = (os.environ.get("CRM_API_KEY") or "").strip()
    usuario = (os.environ.get("CRM_USER") or "").strip()
    password = os.environ.get("CRM_PASSWORD") or ""
    ruta = (os.environ.get("PUNPRO_DB") or "").strip()
    if not url or not ruta or not ((usuario and password) or clave):
        print(json.dumps({"ok": False, "error": "Faltan la cuenta de la empresa o la base"}))
        return 1
    if not os.path.isfile(ruta):
        print(json.dumps({"ok": False, "error": f"No está punpro.db en {ruta}"}))
        return 1
    empresa = (os.environ.get("CRM_EMPRESA_ID") or "").strip()
    nombre_empresa = (os.environ.get("CRM_EMPRESA") or "").strip()
    sucursal_id = (os.environ.get("CRM_SUCURSAL_ID") or "").strip()
    sucursal = (os.environ.get("CRM_SUCURSAL") or "").strip()
    opener = None
    try:
        if usuario and password:
            opener, empresa_login = entrar(url, usuario, password)
            if empresa_login:
                empresa = empresa_login
        elif nombre_empresa:
            empresa = resolver_empresa(url, clave, nombre_empresa)
        clientes = leer_clientes(ruta)
        resultado = enviar(
            url,
            clave,
            clientes,
            empresa_id=empresa or None,
            sucursal_id=sucursal_id or None,
            sucursal=sucursal or None,
            opener=opener,
        )

        def reentrar():
            nonlocal opener, empresa
            nuevo, empresa_login = entrar(url, usuario, password)
            opener = nuevo
            if empresa_login:
                empresa = empresa_login
            return nuevo

        base = subir_base(
            url,
            clave,
            ruta,
            empresa_id=empresa or None,
            sucursal_id=sucursal_id or None,
            sucursal=sucursal or None,
            opener=opener,
            reentrar=reentrar if usuario and password else None,
        )
    except Exception as exc:
        err_msg = str(exc)
        estado_nube.registrar_error(err_msg)
        print(json.dumps({"ok": False, "error": err_msg}, ensure_ascii=False))
        return 1

    if isinstance(resultado, dict):
        resultado.setdefault("ok", not base["errores"])
        resultado["leidos"] = len(clientes)
        resultado["tablas"] = base["tablas"]
        resultado["filas"] = base["filas"]
        resultado["errores_base"] = base["errores"]

    if not base["errores"]:
        estado_nube.registrar_exito(
            tablas=base["tablas"],
            filas=base["filas"],
            empresa=nombre_empresa or usuario,
            sucursal=sucursal,
            mensaje=f"Lote enviado con éxito ({base['tablas']} tablas, {base['filas']} filas)",
        )
    else:
        estado_nube.registrar_error(f"Errores en {len(base['errores'])} tablas.")

    print(json.dumps(resultado, ensure_ascii=False))
    return 0 if not base["errores"] else 1

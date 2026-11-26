"""
Motor Incremental de Sincronización TPV Pro 2026 -> Cobro Fácil.
Protocolo nuevo:
1. Identificación automática de PC (machine_id único persistente + nombre_pc).
2. Saludo Liviano (Heartbeat) -> Esperar habilitación desde la Web.
3. Subida Incremental de Tickets + Manejo de faltantes.
4. Subida de Inventario con ID único y código de barras / PLU opcional.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import socket
import sqlite3
import sys
import time
import urllib.error
import urllib.request
import uuid
from typing import Any

logger = logging.getLogger("crm_incremental")

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))


def obtener_config_path() -> str:
    return os.path.join(RAIZ, "config.json")


def obtener_o_crear_machine_id() -> tuple[str, str]:
    """Obtiene o genera un machine_id persistente y el nombre_pc."""
    cfg_path = obtener_config_path()
    cfg = {}
    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}

    m_id = str(cfg.get("machine_id") or "").strip()
    locks_dir = os.path.join(RAIZ, "locks")
    os.makedirs(locks_dir, exist_ok=True)
    m_id_file = os.path.join(locks_dir, "machine_id.txt")

    if not m_id and os.path.isfile(m_id_file):
        try:
            with open(m_id_file, "r", encoding="utf-8") as f:
                m_id = f.read().strip()
        except Exception:
            m_id = ""

    if not m_id:
        m_id = str(uuid.uuid4())
        cfg["machine_id"] = m_id
        try:
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=4)
        except Exception:
            pass
        try:
            with open(m_id_file, "w", encoding="utf-8") as f:
                f.write(m_id)
        except Exception:
            pass

    nombre_pc = str(cfg.get("machine_hostname") or platform.node() or socket.gethostname() or "TPV-PC").strip()
    return m_id, nombre_pc


def _is_port_open(host: str, port: int = 3306, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _safe_float(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        if isinstance(val, str):
            val = val.strip().replace(",", ".")
            if not val:
                return default
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_int(val: Any, default: int = 0) -> int:
    if val is None:
        return default
    try:
        if isinstance(val, str):
            val = val.strip()
            if not val:
                return default
        return int(float(val))
    except (ValueError, TypeError):
        return default


def obtener_version_pos() -> str:
    ver_path = os.path.join(RAIZ, "version.json")
    if os.path.isfile(ver_path):
        try:
            with open(ver_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return str(data.get("app_version") or data.get("version") or "v50.63")
        except Exception:
            pass
    return "v50.63"


def obtener_conexiones_bd():
    """Devuelve (conn_sqlite, conn_mariadb)."""
    cfg_path = obtener_config_path()
    cfg = {}
    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}

    ruta_sqlite = str(cfg.get("punpro_db") or os.path.join(RAIZ, "punpro.db")).strip()
    conn_sq = None
    if os.path.isfile(ruta_sqlite):
        try:
            conn_sq = sqlite3.connect(ruta_sqlite)
            conn_sq.row_factory = sqlite3.Row
        except Exception as e:
            logger.warning("Error conectando a SQLite: %s", e)

    conn_my = None
    try:
        import pymysql
        hosts_a_probar = []
        for h in [cfg.get("preferred_master_ip"), cfg.get("carteleria_master_ip"), cfg.get("db_host"), "192.168.0.8", "192.168.0.13", "127.0.0.1", "localhost"]:
            h_str = str(h or "").strip()
            if h_str and h_str not in hosts_a_probar:
                hosts_a_probar.append(h_str)

        port = int(cfg.get("db_port") or cfg.get("mariadb_port") or 3306)
        hosts_vivos = [h for h in hosts_a_probar if _is_port_open(h, port=port, timeout=0.3)]

        if hosts_vivos:
            passwords_a_probar = []
            for p in [cfg.get("db_pass"), cfg.get("mariadb_password"), "1234", ""]:
                if p is not None and p not in passwords_a_probar:
                    passwords_a_probar.append(p)

            dbs_a_probar = []
            for d in [cfg.get("db_name"), "punpro_db", "punpro"]:
                d_str = str(d or "").strip()
                if d_str and d_str not in dbs_a_probar:
                    dbs_a_probar.append(d_str)

            candidatos = []
            for host in hosts_vivos:
                for password in passwords_a_probar:
                    for db in dbs_a_probar:
                        try:
                            conn_test = pymysql.connect(
                                host=host,
                                port=port,
                                user=str(cfg.get("db_user") or "root").strip(),
                                password=password,
                                database=db,
                                cursorclass=pymysql.cursors.DictCursor,
                                connect_timeout=1
                            )
                            c_test = conn_test.cursor()
                            c_test.execute("SELECT MAX(id) as max_id FROM ventas")
                            r = c_test.fetchone()
                            m_id = r.get("max_id") if r and r.get("max_id") else 0
                            candidatos.append((m_id, host, conn_test))
                            break
                        except Exception:
                            pass
                    if any(c[1] == host for c in candidatos):
                        break

            if candidatos:
                candidatos.sort(key=lambda x: x[0], reverse=True)
                mejor_id, mejor_host, conn_my = candidatos[0]
                logger.info("Conectado a MariaDB en %s (max_id: %s)", mejor_host, mejor_id)
                for _, h, c in candidatos[1:]:
                    try:
                        c.close()
                    except Exception:
                        pass
    except Exception as e:
        logger.debug("MariaDB offline o sin pymysql: %s", e)

    return conn_sq, conn_my


def enviar_post_json(url: str, payload: dict, timeout: int = 30) -> tuple[int, dict]:
    """Envía un POST JSON con urllib nativo y devuelve (status_code, response_dict)."""
    data_bytes = json.dumps(payload, default=str).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data_bytes,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            try:
                parsed = json.loads(body)
                if not isinstance(parsed, dict):
                    parsed = {"raw": parsed}
                return resp.status, parsed
            except json.JSONDecodeError:
                return resp.status, {"raw": body}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        try:
            parsed = json.loads(body)
            if not isinstance(parsed, dict):
                parsed = {"error": str(parsed)}
            return e.code, parsed
        except Exception:
            return e.code, {"error": body}
    except Exception as e:
        return 0, {"error": str(e)}


def paso1_saludo(crm_url: str, empresa_usuario: str, machine_id: str, nombre_pc: str, version_pos: str) -> dict:
    """Paso 1: Saludo liviano (Heartbeat)."""
    url = f"{crm_url.rstrip('/')}/api/pos/terminal/saludo"
    payload = {
        "empresa_usuario": empresa_usuario,
        "machine_id": machine_id,
        "nombre_pc": nombre_pc,
        "version_pos": version_pos
    }
    status, resp = enviar_post_json(url, payload, timeout=15)
    if not isinstance(resp, dict):
        resp = {"raw": str(resp)}
    if status == 200:
        return resp
    elif status in (401, 403):
        return {"habilitada": False, "revocada": True, "error": resp.get("error", "Acceso denegado")}
    else:
        return {"habilitada": False, "error": resp.get("error", f"HTTP {status}")}


def paso2_tickets_incrementales(crm_url: str, empresa_usuario: str, machine_id: str, sucursal_id: int, conn_sq, conn_my=None) -> dict:
    """Paso 2: Subida incremental de tickets nuevos/modificados y manejo de faltantes."""
    locks_dir = os.path.join(RAIZ, "locks")
    os.makedirs(locks_dir, exist_ok=True)
    ticket_lock_file = os.path.join(locks_dir, "crm_ultimo_ticket.txt")

    ultimo_id = 0
    if os.path.isfile(ticket_lock_file):
        try:
            with open(ticket_lock_file, "r", encoding="utf-8") as f:
                ultimo_id = int(f.read().strip() or "0")
        except Exception:
            ultimo_id = 0

    # Determinar qué base tiene los tickets más recientes (MariaDB de la maestra o SQLite local)
    cursor = None
    es_sqlite = True
    max_sq = 0
    if conn_sq:
        try:
            c = conn_sq.cursor()
            c.execute("SELECT MAX(id) FROM ventas")
            row = c.fetchone()
            max_sq = row[0] if row and row[0] else 0
        except Exception:
            max_sq = 0

    max_my = 0
    if conn_my:
        try:
            c = conn_my.cursor()
            c.execute("SELECT MAX(id) as max_id FROM ventas")
            row = c.fetchone()
            max_my = row.get("max_id") if row and row.get("max_id") else 0
        except Exception:
            max_my = 0

    if max_my >= max_sq and conn_my and max_my > 0:
        cursor = conn_my.cursor()
        es_sqlite = False
        logger.info("Usando MariaDB para tickets (max_id: %s vs sqlite: %s)", max_my, max_sq)
    elif conn_sq:
        cursor = conn_sq.cursor()
        es_sqlite = True
        logger.info("Usando SQLite para tickets (max_id: %s)", max_sq)
    elif conn_my:
        cursor = conn_my.cursor()
        es_sqlite = False
        logger.info("Usando MariaDB fallback (max_id: %s)", max_my)

    if not cursor:
        return {"ok": False, "error": "Sin conexión a base local"}

    # Si ultimo_id es 0, buscar desde dónde sincronizar (por ejemplo últimas 200 ventas o todas)
    param = (ultimo_id,)
    query_v = "SELECT * FROM ventas WHERE id > ? ORDER BY id ASC LIMIT 100" if es_sqlite else "SELECT * FROM ventas WHERE id > %s ORDER BY id ASC LIMIT 100"
    cursor.execute(query_v, param)
    ventas = cursor.fetchall()

    if not ventas:
        return {"ok": True, "procesados": 0, "mensaje": "Sin tickets nuevos"}

    ticket_ids = [v["id"] for v in ventas]
    # Traer detalles_ventas para estos tickets
    detalles_por_venta: dict[Any, list] = {tid: [] for tid in ticket_ids}
    placeholders = ",".join("?" if es_sqlite else "%s" for _ in ticket_ids)
    query_d = f"SELECT * FROM detalles_ventas WHERE id_venta IN ({placeholders})"
    cursor.execute(query_d, tuple(ticket_ids))
    for d in cursor.fetchall():
        d_dict = dict(d)
        iv = d_dict.get("id_venta")
        if iv in detalles_por_venta:
            detalles_por_venta[iv].append(d_dict)

    tickets_payload = []
    resumen_diario_map: dict[str, dict] = {}

    for v in ventas:
        v_dict = dict(v)
        nro = v_dict["id"]
        req_id = v_dict.get("request_id")
        t_uuid = str(req_id) if req_id else str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{machine_id}-{nro}"))
        estado_raw = str(v_dict.get("estado") or "CERRADA").upper()
        es_canc = estado_raw in ("CANCELADA", "CANCELADO")
        tot = 0.0 if es_canc else _safe_float(v_dict.get("total"))
        metodo = str(v_dict.get("metodo_pago") or "Efectivo")
        fecha_str = str(v_dict.get("fecha") or "")

        dia_k = fecha_str[:10]
        if dia_k:
            if dia_k not in resumen_diario_map:
                resumen_diario_map[dia_k] = {"fecha": dia_k, "cantidad_tickets": 0, "monto_total": 0.0}
            resumen_diario_map[dia_k]["cantidad_tickets"] += 1
            resumen_diario_map[dia_k]["monto_total"] += tot

        items = []
        for det in detalles_por_venta.get(nro, []):
            items.append({
                "id_producto": str(det.get("id_producto") or ""),
                "nombre": str(det.get("nombre_producto") or ""),
                "cantidad": _safe_float(det.get("cantidad"), 1.0),
                "precio": _safe_float(det.get("precio_unitario")),
                "subtotal": _safe_float(det.get("subtotal"))
            })

        tickets_payload.append({
            "machine_id": machine_id,
            "nro_ticket": nro,
            "ticket_uuid": t_uuid,
            "fecha_hora": fecha_str,
            "total": tot,
            "metodo_pago": metodo,
            "estado": "CANCELADO" if es_canc else "ACTIVO",
            "items": items
        })

    url = f"{crm_url.rstrip('/')}/api/pos/tickets/incremental"
    payload = {
        "empresa_usuario": empresa_usuario,
        "machine_id": machine_id,
        "sucursal_id": sucursal_id,
        "tickets": tickets_payload,
        "resumen_diario": list(resumen_diario_map.values()),
        "no_encontrados": []
    }

    status, resp = enviar_post_json(url, payload, timeout=60)
    if status == 200 and resp.get("ok"):
        # Actualizar último ticket id
        nuevo_max = max(ticket_ids)
        try:
            with open(ticket_lock_file, "w", encoding="utf-8") as f:
                f.write(str(nuevo_max))
        except Exception:
            pass

        # Manejo de tickets faltantes solicitados por la nube
        faltantes = resp.get("tickets_faltantes") or []
        if faltantes:
            _resolver_faltantes(crm_url, empresa_usuario, machine_id, sucursal_id, faltantes, cursor, es_sqlite)

        return resp
    else:
        return {"ok": False, "error": resp.get("error", f"HTTP {status}")}


def _resolver_faltantes(crm_url: str, empresa_usuario: str, machine_id: str, sucursal_id: int, faltantes: list[int], cursor, es_sqlite: bool):
    """Busca números de ticket específicos solicitados por la nube."""
    if not faltantes:
        return
    placeholders = ",".join("?" if es_sqlite else "%s" for _ in faltantes)
    cursor.execute(f"SELECT * FROM ventas WHERE id IN ({placeholders})", tuple(faltantes))
    encontrados = cursor.fetchall()
    encontrados_ids = {v["id"] for v in encontrados}
    no_enc = [f for f in faltantes if f not in encontrados_ids]

    if not encontrados:
        if no_enc:
            # Informar que no están en esta máquina
            url = f"{crm_url.rstrip('/')}/api/pos/tickets/incremental"
            enviar_post_json(url, {
                "empresa_usuario": empresa_usuario,
                "machine_id": machine_id,
                "sucursal_id": sucursal_id,
                "tickets": [],
                "no_encontrados": no_enc
            }, timeout=30)
        return

    # Si hay encontrados, armar y enviar
    # (Misma estructura)
    ticket_ids = [v["id"] for v in encontrados]
    placeholders_d = ",".join("?" if es_sqlite else "%s" for _ in ticket_ids)
    cursor.execute(f"SELECT * FROM detalles_ventas WHERE id_venta IN ({placeholders_d})", tuple(ticket_ids))
    detalles_por_venta = {tid: [] for tid in ticket_ids}
    for d in cursor.fetchall():
        d_dict = dict(d)
        iv = d_dict.get("id_venta")
        if iv in detalles_por_venta:
            detalles_por_venta[iv].append(d_dict)

    tickets_payload = []
    for v in encontrados:
        v_dict = dict(v)
        nro = v_dict["id"]
        req_id = v_dict.get("request_id")
        t_uuid = str(req_id) if req_id else str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{machine_id}-{nro}"))
        es_canc = str(v_dict.get("estado") or "").upper() in ("CANCELADA", "CANCELADO")
        tot = 0.0 if es_canc else _safe_float(v_dict.get("total"))

        items = []
        for det in detalles_por_venta.get(nro, []):
            items.append({
                "id_producto": str(det.get("id_producto") or ""),
                "nombre": str(det.get("nombre_producto") or ""),
                "cantidad": _safe_float(det.get("cantidad"), 1.0),
                "precio": _safe_float(det.get("precio_unitario")),
                "subtotal": _safe_float(det.get("subtotal"))
            })

        tickets_payload.append({
            "machine_id": machine_id,
            "nro_ticket": nro,
            "ticket_uuid": t_uuid,
            "fecha_hora": str(v_dict.get("fecha") or ""),
            "total": tot,
            "metodo_pago": str(v_dict.get("metodo_pago") or "Efectivo"),
            "estado": "CANCELADO" if es_canc else "ACTIVO",
            "items": items
        })

    url = f"{crm_url.rstrip('/')}/api/pos/tickets/incremental"
    enviar_post_json(url, {
        "empresa_usuario": empresa_usuario,
        "machine_id": machine_id,
        "sucursal_id": sucursal_id,
        "tickets": tickets_payload,
        "no_encontrados": no_enc
    }, timeout=30)


def paso3_inventario_estructurado(crm_url: str, empresa_usuario: str, machine_id: str, sucursal_id: int, conn_sq, conn_my=None) -> dict:
    """Paso 3: Subida estructurada de inventario de la PC."""
    locks_dir = os.path.join(RAIZ, "locks")
    os.makedirs(locks_dir, exist_ok=True)
    inv_lock_file = os.path.join(locks_dir, "crm_inventario_huella.txt")

    cursor = None
    es_sqlite = True
    if conn_my:
        cursor = conn_my.cursor()
        es_sqlite = False
    elif conn_sq:
        cursor = conn_sq.cursor()
        es_sqlite = True

    if not cursor:
        return {"ok": False, "error": "Sin conexión a base local"}

    cursor.execute("SELECT id, nombre, precio, stock, codigo, departamento, es_pesable FROM productos")
    prods = cursor.fetchall()
    if not prods:
        return {"ok": True, "articulos_procesados": 0}

    articulos = []
    cadena_huella = []
    for p in prods:
        p_dict = dict(p)
        id_u = p_dict["id"]
        cod = str(p_dict.get("codigo") or "").strip()
        es_pes = int(p_dict.get("es_pesable") or 0)
        # Si tiene balanza/pesable y código corto, es código PLU
        cod_plu = cod if es_pes and len(cod) <= 5 else None
        cod_barras = cod if (not es_pes or len(cod) > 5) else None

        art = {
            "machine_id": machine_id,
            "id_unico": id_u,
            "codigo_barras": cod_barras,
            "codigo_plu": cod_plu,
            "nombre": str(p_dict.get("nombre") or ""),
            "departamento": str(p_dict.get("departamento") or "GENERAL"),
            "precio": _safe_float(p_dict.get("precio")),
            "stock": _safe_float(p_dict.get("stock")),
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        articulos.append(art)
        cadena_huella.append(f"{id_u}:{art['precio']}:{art['stock']}:{cod}")

    import hashlib
    huella_actual = hashlib.sha256(";".join(cadena_huella).encode("utf-8")).hexdigest()

    huella_previa = ""
    if os.path.isfile(inv_lock_file):
        try:
            with open(inv_lock_file, "r", encoding="utf-8") as f:
                huella_previa = f.read().strip()
        except Exception:
            huella_previa = ""

    if huella_actual == huella_previa:
        return {"ok": True, "articulos_procesados": 0, "mensaje": "Inventario sin cambios"}

    url = f"{crm_url.rstrip('/')}/api/pos/inventario/sync"
    payload = {
        "empresa_usuario": empresa_usuario,
        "machine_id": machine_id,
        "sucursal_id": sucursal_id,
        "articulos": articulos
    }

    status, resp = enviar_post_json(url, payload, timeout=60)
    if status == 200 and resp.get("ok"):
        try:
            with open(inv_lock_file, "w", encoding="utf-8") as f:
                f.write(huella_actual)
        except Exception:
            pass
        return resp
    else:
        return {"ok": False, "error": resp.get("error", f"HTTP {status}")}


def paso4_cuenta_corriente_incrementales(crm_url: str, empresa_usuario: str, machine_id: str, sucursal_id: int, conn_sq, conn_my=None) -> dict:
    """Paso 4: Subida incremental de movimientos de cuenta corriente (pagos/abonos/cargos)."""
    locks_dir = os.path.join(RAIZ, "locks")
    os.makedirs(locks_dir, exist_ok=True)
    cc_lock_file = os.path.join(locks_dir, "crm_ultimo_movimiento_cc.txt")

    ultimo_id = 0
    if os.path.isfile(cc_lock_file):
        try:
            with open(cc_lock_file, "r", encoding="utf-8") as f:
                ultimo_id = int(f.read().strip() or "0")
        except Exception:
            ultimo_id = 0

    cursor = None
    es_sqlite = True
    max_sq = 0
    if conn_sq:
        try:
            c = conn_sq.cursor()
            c.execute("SELECT MAX(id) FROM cuenta_corriente")
            row = c.fetchone()
            max_sq = row[0] if row and row[0] else 0
        except Exception:
            max_sq = 0

    max_my = 0
    if conn_my:
        try:
            c = conn_my.cursor()
            c.execute("SELECT MAX(id) as max_id FROM cuenta_corriente")
            row = c.fetchone()
            max_my = row.get("max_id") if row and row.get("max_id") else 0
        except Exception:
            max_my = 0

    if max_my >= max_sq and conn_my and max_my > 0:
        cursor = conn_my.cursor()
        es_sqlite = False
        logger.info("Usando MariaDB para cuenta corriente (max_id: %s)", max_my)
    elif conn_sq:
        cursor = conn_sq.cursor()
        es_sqlite = True
        logger.info("Usando SQLite para cuenta corriente (max_id: %s)", max_sq)
    elif conn_my:
        cursor = conn_my.cursor()
        es_sqlite = False

    if not cursor:
        return {"ok": False, "error": "Sin conexión a base local"}

    query = (
        "SELECT * FROM cuenta_corriente WHERE id > ? ORDER BY id ASC LIMIT 200"
        if es_sqlite else
        "SELECT * FROM cuenta_corriente WHERE id > %s ORDER BY id ASC LIMIT 200"
    )
    cursor.execute(query, (ultimo_id,))
    movs = cursor.fetchall()
    if not movs:
        return {"ok": True, "procesados": 0, "mensaje": "Sin movimientos CC nuevos"}

    movimientos_payload = []
    cc_ids = []
    for m in movs:
        m_dict = dict(m)
        mid = m_dict.get("id")
        cc_ids.append(mid)
        movimientos_payload.append({
            "id": mid,
            "cliente_id": m_dict.get("cliente_id"),
            "fecha": str(m_dict.get("fecha") or ""),
            "tipo": str(m_dict.get("tipo") or "ABONO"),
            "monto": _safe_float(m_dict.get("monto")),
            "saldo_resultante": _safe_float(m_dict.get("saldo_resultante")),
            "descripcion": str(m_dict.get("descripcion") or ""),
            "venta_id": m_dict.get("venta_id"),
            "medio_pago": str(m_dict.get("medio_pago") or ""),
            "perfil": str(m_dict.get("perfil") or ""),
            "registrado_por": str(m_dict.get("registrado_por") or "")
        })

    url = f"{crm_url.rstrip('/')}/api/pos/cuenta-corriente/incremental"
    payload = {
        "empresa_usuario": empresa_usuario,
        "machine_id": machine_id,
        "sucursal_id": sucursal_id,
        "movimientos": movimientos_payload
    }
    status, resp = enviar_post_json(url, payload, timeout=30)
    if status == 200 and resp.get("ok"):
        nuevo_max = max(cc_ids)
        try:
            with open(cc_lock_file, "w", encoding="utf-8") as f:
                f.write(str(nuevo_max))
        except Exception:
            pass
        return resp
    else:
        return {"ok": False, "error": resp.get("error", f"HTTP {status}")}


def paso5_cartera_clientes_sync(crm_url: str, empresa_usuario: str, machine_id: str, sucursal_id: int, conn_sq, conn_my=None) -> dict:
    """Paso 5: Sincronización de cartera de clientes (saldos y deudas actualizadas)."""
    locks_dir = os.path.join(RAIZ, "locks")
    os.makedirs(locks_dir, exist_ok=True)
    cli_lock_file = os.path.join(locks_dir, "crm_clientes_huella.txt")

    cursor = None
    es_sqlite = True
    if conn_my:
        cursor = conn_my.cursor()
        es_sqlite = False
    elif conn_sq:
        cursor = conn_sq.cursor()
        es_sqlite = True

    if not cursor:
        return {"ok": False, "error": "Sin conexión a base local"}

    cursor.execute("SELECT * FROM clientes")
    clientes_rows = cursor.fetchall()
    if not clientes_rows:
        return {"ok": True, "clientes_procesados": 0}

    import hashlib
    clientes_payload = []
    cadena_huella = []
    for c in clientes_rows:
        c_dict = dict(c)
        cid = c_dict.get("id")
        nom = str(c_dict.get("nombre") or "").strip()
        if not nom:
            continue
        deuda = _safe_float(c_dict.get("deuda_actual") if c_dict.get("deuda_actual") is not None else c_dict.get("saldo"))
        limite = _safe_float(c_dict.get("limite_credito"))
        tel = str(c_dict.get("telefono") or "")
        dni = str(c_dict.get("dni") or "")
        dire = str(c_dict.get("direccion") or "")
        tc = str(c_dict.get("tipo_cliente") or "regular")
        plazo = _safe_int(c_dict.get("plazo_dias"))
        est = str(c_dict.get("estado_cuenta") or "activo")

        clientes_payload.append({
            "id": cid,
            "nombre": nom,
            "deuda_actual": deuda,
            "limite_credito": limite,
            "telefono": tel,
            "dni": dni,
            "direccion": dire,
            "tipo_cliente": tc,
            "plazo_dias": plazo,
            "estado_cuenta": est,
            "sucursal_id": sucursal_id,
            "machine_id": machine_id
        })
        cadena_huella.append(f"{cid}:{nom}:{deuda}:{limite}:{tel}")

    huella_actual = hashlib.sha256(";".join(cadena_huella).encode("utf-8")).hexdigest()
    huella_previa = ""
    if os.path.isfile(cli_lock_file):
        try:
            with open(cli_lock_file, "r", encoding="utf-8") as f:
                huella_previa = f.read().strip()
        except Exception:
            huella_previa = ""

    if huella_actual == huella_previa:
        return {"ok": True, "clientes_procesados": 0, "mensaje": "Cartera de clientes sin cambios"}

    url = f"{crm_url.rstrip('/')}/api/pos/clientes/lote"
    payload = {
        "empresa_usuario": empresa_usuario,
        "machine_id": machine_id,
        "sucursal_id": sucursal_id,
        "clientes": clientes_payload
    }
    status, resp = enviar_post_json(url, payload, timeout=45)
    if status == 200 and resp.get("ok"):
        try:
            with open(cli_lock_file, "w", encoding="utf-8") as f:
                f.write(huella_actual)
        except Exception:
            pass
        return resp
    else:
        return {"ok": False, "error": resp.get("error", f"HTTP {status}")}


def ciclo_sincronizacion_completo(crm_url: str = "https://crm-frigorifico.onrender.com", empresa_usuario: str = "maciel") -> dict:
    """
    Ejecuta el ciclo de 5 pasos:
    1. Saludo liviano -> Obtener sucursal_id
    2. Si habilitada == true -> Subida incremental de tickets
    3. Si habilitada == true -> Subida estructurada de inventario
    4. Si habilitada == true -> Subida incremental de cuenta corriente (pagos/abonos)
    5. Si habilitada == true -> Sincronización de cartera de clientes
    """
    m_id, nombre_pc = obtener_o_crear_machine_id()
    ver_pos = obtener_version_pos()

    # Paso 1: Saludo
    saludo = paso1_saludo(crm_url, empresa_usuario, m_id, nombre_pc, ver_pos)
    if not saludo.get("habilitada"):
        return {
            "ok": False,
            "fase": "saludo",
            "habilitada": False,
            "mensaje": saludo.get("mensaje") or saludo.get("error") or "Terminal no habilitada"
        }

    suc_id = saludo["sucursal_id"]
    nombre_suc = saludo.get("nombre_sucursal") or f"Sucursal {suc_id}"

    # Pasos 2 a 5: Conectar BD
    conn_sq, conn_my = obtener_conexiones_bd()
    try:
        res_tickets = paso2_tickets_incrementales(crm_url, empresa_usuario, m_id, suc_id, conn_sq, conn_my)
        res_inv = paso3_inventario_estructurado(crm_url, empresa_usuario, m_id, suc_id, conn_sq, conn_my)
        res_cc = paso4_cuenta_corriente_incrementales(crm_url, empresa_usuario, m_id, suc_id, conn_sq, conn_my)
        res_cli = paso5_cartera_clientes_sync(crm_url, empresa_usuario, m_id, suc_id, conn_sq, conn_my)
    finally:
        if conn_sq:
            try:
                conn_sq.close()
            except Exception:
                pass
        if conn_my:
            try:
                conn_my.close()
            except Exception:
                pass

    return {
        "ok": True,
        "fase": "completo",
        "habilitada": True,
        "machine_id": m_id,
        "nombre_pc": nombre_pc,
        "sucursal_id": suc_id,
        "nombre_sucursal": nombre_suc,
        "tickets": res_tickets,
        "inventario": res_inv,
        "cuenta_corriente": res_cc,
        "clientes": res_cli
    }

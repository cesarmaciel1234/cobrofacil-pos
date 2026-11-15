"""Pruebas unitarias para la Mini Web moderna de enlace Nube & CRM y sus motores."""

import json
import os
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from src.central_red_global.servidor.crm_salida.motor.bajada import (
    aplicar_novedades_en_staging,
    consultar_novedades_nube,
)
from src.central_red_global.servidor.crm_salida.motor.estado import GestorEstado
from src.central_red_global.servidor.crm_salida.web.servidor_web import (
    detener_servidor_web,
    iniciar_servidor_web,
    obtener_url_web,
)


@pytest.fixture(autouse=True)
def cleanup_web():
    from src.config import config
    from src.central_red_global.servidor.crm_salida.motor.estado import estado_nube
    url_orig = config.get("crm_url")
    user_orig = config.get("crm_usuario")
    suc_orig = config.get("crm_sucursal")
    suc_id_orig = config.get("crm_sucursal_id")
    yield
    detener_servidor_web()
    try:
        if url_orig:
            config.set("crm_url", url_orig)
        if user_orig:
            config.set("crm_usuario", user_orig)
        if suc_orig:
            config.set("crm_sucursal", suc_orig)
        if suc_id_orig:
            config.set("crm_sucursal_id", suc_id_orig)
        estado_nube.registrar_sucursal_local(suc_id_orig or "1", suc_orig or "")
    except Exception:
        pass


def test_miniweb_servidor_levanta_y_responde_html():
    url = obtener_url_web()
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200
        contenido = resp.read().decode("utf-8")
        assert "Cobro Fácil" in contenido
        assert "Nombre de Sucursal" in contenido
        assert "Obligatorio" in contenido


def test_miniweb_api_estado():
    url = obtener_url_web()
    req = urllib.request.Request(f"{url}/api/estado", method="GET")
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "conectado" in data
        assert "estado_texto" in data


def test_miniweb_conectar_sucursal_obligatoria():
    url = obtener_url_web()
    req = urllib.request.Request(
        f"{url}/api/conectar",
        data=json.dumps({
            "url": "https://crm-frigorifico.onrender.com",
            "empresa": "maciel",
            "password": "pass",
            "sucursal_id": "1",
            "sucursal": "",  # Vacía a propósito
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req, timeout=5)
    assert exc_info.value.code == 400
    res = json.loads(exc_info.value.read().decode("utf-8"))
    assert res["ok"] is False
    assert "sucursal" in res["error"].lower()


def test_miniweb_conectar_exito_con_mock_cloud():
    # Mock cloud server que responde a /auth/login
    class CloudMock(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path == "/auth/login":
                cuerpo = b'{"ok": true, "user": {"empresa_id": "100", "username": "maciel"}}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Set-Cookie", "session=mock_cookie; Path=/")
                self.end_headers()
                self.wfile.write(cuerpo)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *args):
            pass

    cloud = ThreadingHTTPServer(("127.0.0.1", 0), CloudMock)
    hilo = threading.Thread(target=cloud.serve_forever, daemon=True)
    hilo.start()
    try:
        cloud_port = cloud.server_address[1]
        url = obtener_url_web()
        req = urllib.request.Request(
            f"{url}/api/conectar",
            data=json.dumps({
                "url": f"http://127.0.0.1:{cloud_port}",
                "empresa": "maciel",
                "password": "clave_correcta",
                "sucursal_id": "1",
                "sucursal": "Casa Central",
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["ok"] is True
            assert data["estado"]["conectado"] is True
            assert data["estado"]["sucursal"] == "Casa Central"
    finally:
        cloud.shutdown()


def test_bajada_staging(tmp_path):
    ruta_staging = str(tmp_path / "novedades_staging.json")
    novedades = {
        "precios": [{"id": 1, "precio": 1500.0}],
        "clientes": [{"id": 5, "nombre": "Cliente Nube"}],
    }
    ok = aplicar_novedades_en_staging(novedades, ruta_staging=ruta_staging)
    assert ok is True
    assert os.path.isfile(ruta_staging)
    with open(ruta_staging, "r", encoding="utf-8") as f:
        datos = json.load(f)
        assert datos["contenido"]["precios"][0]["precio"] == 1500.0

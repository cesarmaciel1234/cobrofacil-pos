import time
from unittest.mock import MagicMock, patch

from src.central_red_global.servidor.crm_salida.motor.estado import GestorEstado
from src.central_red_global.servidor.crm_salida.motor.subida import medir_latencia
from src.central_red_global.servidor.crm_salida.vigilante import notificar_venta, pedir_vuelta


def test_gestor_estado_latencia_y_progreso():
    estado = GestorEstado()
    estado.registrar_latencia(45.67)
    datos = estado.obtener_estado()
    assert datos.get("latencia_ms") == 45.7

    estado.registrar_en_progreso("Transfiriendo deltas...")
    datos = estado.obtener_estado()
    assert datos.get("sincronizando") is True

    estado.registrar_exito(tablas=10, filas=150, tickets=1200, clientes=450, duracion_seg=1.23)
    datos = estado.obtener_estado()
    assert datos.get("sincronizando") is False
    assert datos.get("conectado") is True
    assert datos.get("tablas_totales") == 10
    assert datos.get("filas_totales") == 150
    assert datos.get("tickets_totales") == 1200
    assert datos.get("clientes_totales") == 450
    assert datos.get("duracion_segundos") == 1.23


def test_medir_latencia_url_vacia():
    assert medir_latencia("") is None
    assert medir_latencia(None) is None


def test_medir_latencia_mock():
    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"ok": true}'
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=mock_resp):
        lat = medir_latencia("https://crm-frigorifico.onrender.com")
        assert lat is not None
        assert lat >= 0


def test_notificar_venta_y_pedir_vuelta():
    with patch("src.central_red_global.servidor.crm_salida.vigilante.pedir_vuelta") as mock_pedir:
        notificar_venta(retraso_seg=0.05)
        time.sleep(0.1)
        mock_pedir.assert_called_with(forzar=True)


def test_panel_nativo_bloqueo_y_lapiz():
    from PyQt6.QtWidgets import QApplication
    from src.central_red_global.servidor.ventana.panel_nativo import PanelNativoCRM

    _app = QApplication.instance() or QApplication([])

    with patch("src.config.config.get", side_effect=lambda k: "maciel" if "crm" in k else ""):
        panel = PanelNativoCRM()
        # Con datos existentes, debe arrancar bloqueado
        assert panel._modo_edicion is False
        assert panel.txt_url.isReadOnly() is True
        assert panel.txt_empresa.isReadOnly() is True
        assert panel.txt_password.isReadOnly() is True
        assert panel.txt_sucursal.isReadOnly() is True
        assert "Sincronizar" in panel.btn_conectar.text()

        # Al tocar el lápiz, se activa la edición
        panel.btn_lapiz.click()
        assert panel._modo_edicion is True
        assert panel.txt_empresa.isReadOnly() is False
        assert "Guardar" in panel.btn_conectar.text()

        # Al volver a tocar, se bloquea de nuevo
        panel.btn_lapiz.click()
        assert panel._modo_edicion is False
        assert panel.txt_empresa.isReadOnly() is True


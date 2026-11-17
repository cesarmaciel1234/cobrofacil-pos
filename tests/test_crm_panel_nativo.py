"""Pruebas unitarias para el Panel Nativo del CRM y la ventana de enlace."""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication(sys.argv)

from src.central_red_global.servidor.ventana.panel_nativo import PanelNativoCRM
from src.central_red_global.servidor.ventana.crm import VentanaMiniWebCRM


def test_panel_nativo_instancia_y_campos():
    panel = PanelNativoCRM()
    assert panel.txt_url is not None
    assert panel.txt_empresa is not None
    assert panel.txt_password is not None
    assert panel.txt_sucursal is not None
    assert panel.txt_sucursal_id is not None
    assert panel.btn_conectar is not None
    panel.deleteLater()


def test_panel_nativo_valida_sucursal_obligatoria():
    panel = PanelNativoCRM()
    panel.txt_url.setText("https://crm-frigorifico.onrender.com")
    panel.txt_empresa.setText("maciel")
    panel.txt_password.setText("12345678")
    panel.txt_sucursal.setText("")  # Vacío a propósito

    panel._al_click_conectar()

    assert not panel.caja_error.isHidden()
    assert "obligatorio" in panel.lbl_err_msg.text().lower()
    panel.deleteLater()


def test_ventana_miniweb_usa_panel_nativo_si_falla_webengine():
    ventana = VentanaMiniWebCRM(url_web="http://127.0.0.1:8120")
    assert ventana._panel_nativo is not None
    assert isinstance(ventana._panel_nativo, PanelNativoCRM)
    ventana.deleteLater()


def test_panel_nativo_guarda_cambio_sucursal_inmediato():
    from src.config import config

    suc_ant = config.get("crm_sucursal")
    try:
        panel = PanelNativoCRM()
        panel.txt_sucursal.setText("Nueva Sucursal Test")
        panel.txt_sucursal_id.setText("5")
        panel._guardar_config_local_silencioso()

        assert config.get("crm_sucursal") == "Nueva Sucursal Test"
        assert str(config.get("crm_sucursal_id")) == "5"
        panel.deleteLater()
    finally:
        if suc_ant:
            config.set("crm_sucursal", suc_ant)
            config.set("crm_sucursal_id", "1")


def test_evaluar_disponibilidad_id():
    panel = PanelNativoCRM()
    panel._al_recibir_sucursales([
        {"id": 1, "nombre": "Maciel"},
        {"id": 2, "nombre": "alfaro 1954"},
    ])

    # Caso 1: ID 2 coincide
    panel.txt_sucursal_id.setText("2")
    panel.txt_sucursal.setText("alfaro 1954")
    panel._evaluar_disponibilidad_id()
    assert "asignado" in panel.lbl_sucursal_info.text().lower()

    # Caso 2: ID 3 disponible
    panel.txt_sucursal_id.setText("3")
    panel.txt_sucursal.setText("Sucursal Nueva")
    panel._evaluar_disponibilidad_id()
    assert "disponible" in panel.lbl_sucursal_info.text().lower()

    panel.deleteLater()


def test_auto_pc_y_siguiente_id_calculo():
    from src.central_red_global.servidor.ventana.panel_nativo import calcular_siguiente_id

    # Sin sucursales previas
    assert calcular_siguiente_id([]) == "1"
    assert calcular_siguiente_id(None) == "1"

    # Con sucursal 1 ocupada -> siguiente es 2
    assert calcular_siguiente_id([{"id": 1, "nombre": "Maciel"}]) == "2"

    # Con sucursales 1, 2, 5 -> siguiente es 6
    assert calcular_siguiente_id([
        {"id": 1, "nombre": "Maciel"},
        {"id": 2, "nombre": "Sucursal 2"},
        {"id": 5, "nombre": "Sucursal 5"},
    ]) == "6"


def test_auto_pc_boton_agrega_nombre_maquina_y_siguiente_id(monkeypatch):
    from src.config import config
    from src.central_red_global.servidor.ventana.panel_nativo import PanelNativoCRM

    suc_ant = config.get("crm_sucursal")
    suc_id_ant = config.get("crm_sucursal_id")
    try:
        monkeypatch.setattr(
            "src.central_red_global.servidor.ventana.panel_nativo.nombre_de_esta_pc",
            lambda: "CAJA-02",
        )
        panel = PanelNativoCRM()
        panel._sucursales_nube = [{"id": 1, "nombre": "Maciel"}]
        panel.txt_sucursal.setText("Maciel")
        panel.txt_sucursal_id.setText("1")

        # Al presionar el botón de auto PC y siguiente ID
        panel.btn_auto_pc.click()

        assert panel.txt_sucursal.text() == "Maciel - CAJA-02"
        assert panel.txt_sucursal_id.text() == "2"
        panel.deleteLater()
    finally:
        if suc_ant is not None:
            config.set("crm_sucursal", suc_ant)
        if suc_id_ant is not None:
            config.set("crm_sucursal_id", suc_id_ant)

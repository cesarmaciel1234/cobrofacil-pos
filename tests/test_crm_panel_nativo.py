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
